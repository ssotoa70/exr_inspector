"""VAST DataEngine handler for exr-inspector.

Triggered by S3 ElementCreated events on a VAST bucket. Downloads EXR files
via boto3 using ctx.secrets, extracts metadata with OpenImageIO, and persists
results to VAST DataBase.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

__version__ = "1.0.0"

logger = logging.getLogger(__name__)

try:
    import OpenImageIO as oiio
except ImportError:  # pragma: no cover - runtime dependency
    oiio = None

try:
    import boto3
except ImportError:  # pragma: no cover - runtime dependency
    boto3 = None

from vast_db_persistence import persist_to_vast_database

SUPPORTED_EXTENSIONS = {".exr"}


@dataclass
class InspectorConfig:
    enable_meta: bool = True
    enable_stats: bool = False
    enable_deep_stats: bool = False
    enable_validate: bool = False
    policy_path: Optional[str] = None
    schema_version: int = 1


def init(ctx):
    """Optional initialization hook for DataEngine runtime."""
    logger.info("exr-inspector %s initialized", __version__)


def handler(ctx, event):
    """Primary DataEngine function handler.

    Receives S3 ElementCreated CloudEvents from a VAST DataEngine trigger.
    Downloads the EXR file from S3 via boto3 using ctx.secrets, inspects it
    with OpenImageIO, and persists metadata to VAST DataBase.
    """
    logger.info("Event received: %s", json.dumps(event, default=str)[:500])

    config = _parse_config(event)

    s3_info = _extract_s3_info(event)
    if s3_info is None:
        return _error_result("Could not extract S3 object info from event")

    object_key = s3_info["object_key"]
    if not _is_supported_extension(object_key):
        return _error_result(f"Unsupported file extension: {object_key}")

    local_path = None
    try:
        local_path = _download_from_s3(ctx, s3_info)

        result: Dict[str, Any] = {
            "schema_version": config.schema_version,
            "file": {},
            "parts": [],
            "channels": [],
            "attributes": {},
            "stats": {},
            "validation": {},
            "errors": [],
            "s3": s3_info,
        }

        if config.enable_meta:
            result["file"] = _collect_file_info(local_path)
            result["file"]["s3_key"] = object_key
            result["file"]["s3_bucket"] = s3_info["bucket_name"]
            exr_meta = _inspect_exr(local_path)
            result["file"].update(exr_meta.get("file", {}))
            result["parts"] = exr_meta.get("parts", [])
            result["channels"] = exr_meta.get("channels", [])
            result["attributes"] = exr_meta.get("attributes", {})
            result["errors"].extend(exr_meta.get("errors", []))

        if config.enable_stats:
            result["stats"] = _stats_placeholder(config.enable_deep_stats)

        if config.enable_validate:
            result["validation"] = _validation_placeholder()

        # Persist to VAST DataBase using ctx for credentials
        persistence_result = persist_to_vast_database(result, event, ctx=ctx)
        result["persistence"] = persistence_result

        return result

    finally:
        if local_path and os.path.exists(local_path):
            os.unlink(local_path)


def _parse_config(event: Dict[str, Any]) -> InspectorConfig:
    data = event.get("data", {}) if isinstance(event, dict) else {}
    return InspectorConfig(
        enable_meta=_coerce_bool(data.get("meta", True)),
        enable_stats=_coerce_bool(data.get("stats", False)),
        enable_deep_stats=_coerce_bool(data.get("deep_stats", False)),
        enable_validate=_coerce_bool(data.get("validate", False)),
        policy_path=data.get("policy_path"),
        schema_version=int(data.get("schema_version", 1)),
    )


def _extract_s3_info(event: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Extract S3 object info from a DataEngine ElementCreated CloudEvent.

    VAST DataEngine element triggers emit CloudEvents wrapping S3 notification
    records (Admin Guide p.200). The S3 record is at:
        event["data"]["Records"][0]["s3"]

    If the event does not contain a CloudEvent "data" wrapper, we also try
    the top-level "Records" key as a fallback.
    """
    if not isinstance(event, dict):
        return None

    # CloudEvent: payload is inside event["data"]["Records"]
    data = event.get("data", event)
    records = data.get("Records", [])
    if not records:
        # Fallback: try top-level Records (in case runtime unwraps envelope)
        records = event.get("Records", [])
    if not records:
        logger.error("No Records found in event payload")
        return None

    if len(records) > 1:
        logger.warning("Event contains %d records; processing first only", len(records))

    record = records[0]
    s3_data = record.get("s3", {})
    obj_info = s3_data.get("object", {})
    bucket_info = s3_data.get("bucket", {})

    object_key = obj_info.get("key", "").strip()
    if not object_key:
        logger.error("Empty S3 object key in event")
        return None

    return {
        "bucket_name": bucket_info.get("name", ""),
        "object_key": object_key,
        "object_size": obj_info.get("size"),
        "etag": obj_info.get("eTag"),
        "event_name": record.get("eventName", ""),
        "event_time": record.get("eventTime", ""),
    }


def _is_supported_extension(object_key: str) -> bool:
    """Check if the S3 object key has a supported file extension."""
    ext = os.path.splitext(object_key)[1].lower()
    return ext in SUPPORTED_EXTENSIONS


def _download_from_s3(ctx: Any, s3_info: Dict[str, Any]) -> str:
    """Download S3 object to local ephemeral storage using ctx.secrets.

    DataEngine functions access S3 credentials through ctx.secrets
    (User Guide p.27). The secret name defaults to 'vast_s3' but can be
    overridden via the VAST_S3_SECRET_NAME environment variable.
    """
    if boto3 is None:
        raise RuntimeError("boto3 is required for S3 access but not installed")

    secret_name = os.environ.get("VAST_S3_SECRET_NAME", "vast_s3")
    try:
        secrets = ctx.secrets[secret_name]
        endpoint = secrets["endpoint"]
        access_key = secrets["access_key"]
        secret_key = secrets["secret_key"]
    except (AttributeError, KeyError, TypeError) as exc:
        raise RuntimeError(
            f"Missing S3 credentials in ctx.secrets['{secret_name}']: {exc}"
        ) from exc

    s3_client = boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
    )

    suffix = os.path.splitext(s3_info["object_key"])[1]
    tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    try:
        logger.info(
            "Downloading s3://%s/%s to %s",
            s3_info["bucket_name"], s3_info["object_key"], tmp.name,
        )
        s3_client.download_file(
            s3_info["bucket_name"], s3_info["object_key"], tmp.name,
        )
        return tmp.name
    except Exception:
        os.unlink(tmp.name)
        raise


def _collect_file_info(path: str) -> Dict[str, Any]:
    info: Dict[str, Any] = {"path": path}
    try:
        stat = os.stat(path)
    except FileNotFoundError:
        return {
            "path": path,
            "error": "File not found",
        }
    except OSError as exc:
        return {
            "path": path,
            "error": f"Stat failed: {exc}",
        }

    info.update(
        {
            "size_bytes": stat.st_size,
            "mtime": _isoformat(stat.st_mtime),
        }
    )
    return info


def _inspect_exr(path: str) -> Dict[str, Any]:
    if oiio is None:
        return {
            "errors": ["OpenImageIO not available in runtime"],
            "parts": [],
            "channels": [],
            "attributes": {},
        }

    image_input = oiio.ImageInput.open(path)
    if image_input is None:
        return {
            "errors": [f"OpenImageIO failed to open file: {path}"],
            "parts": [],
            "channels": [],
            "attributes": {},
        }

    parts: List[Dict[str, Any]] = []
    channels: List[Dict[str, Any]] = []
    part_attributes: List[Dict[str, Any]] = []
    errors: List[str] = []
    subimage = 0

    try:
        while True:
            spec = image_input.spec()
            parts.append(_spec_to_part(spec, subimage))
            channels.extend(_spec_to_channels(spec, subimage))
            part_attributes.append(_attributes_from_spec(spec))

            if not image_input.seek_subimage(subimage + 1, 0):
                break
            subimage += 1
    except Exception as exc:  # pragma: no cover - depends on runtime EXR
        errors.append(f"EXR inspection failed: {exc}")
    finally:
        image_input.close()

    file_meta = {
        "multipart_count": len(parts),
        "is_deep": any(part.get("is_deep") for part in parts),
    }

    return {
        "file": file_meta,
        "parts": parts,
        "channels": channels,
        "attributes": {"parts": part_attributes},
        "errors": errors,
    }


def _spec_to_part(spec: Any, index: int) -> Dict[str, Any]:
    part: Dict[str, Any] = {
        "part_index": index,
        "width": spec.width,
        "height": spec.height,
        "part_name": _get_attr(spec, "name"),
        "view_name": _get_attr(spec, "view"),
        "multi_view": _get_attr(spec, "multiView"),
        "data_window": _serialize_value(_get_attr(spec, "dataWindow")),
        "display_window": _serialize_value(_get_attr(spec, "displayWindow")),
        "pixel_aspect_ratio": _get_attr(spec, "pixelAspectRatio"),
        "line_order": _get_attr(spec, "lineOrder"),
        "compression": _get_attr(spec, "compression"),
        "is_tiled": bool(spec.tile_width),
        "tile_width": spec.tile_width or None,
        "tile_height": spec.tile_height or None,
        "tile_depth": spec.tile_depth or None,
        "is_deep": bool(spec.deep),
    }
    return {key: value for key, value in part.items() if value is not None}


def _spec_to_channels(spec: Any, part_index: int) -> List[Dict[str, Any]]:
    channel_formats = spec.channelformats or []
    x_samples = spec.x_channel_samples or []
    y_samples = spec.y_channel_samples or []
    channels: List[Dict[str, Any]] = []
    for idx, name in enumerate(spec.channelnames):
        if channel_formats and idx < len(channel_formats):
            data_type = _type_desc_to_str(channel_formats[idx])
        else:
            data_type = _type_desc_to_str(spec.format)
        channels.append(
            {
                "part_index": part_index,
                "name": name,
                "type": data_type,
                "x_sampling": x_samples[idx] if idx < len(x_samples) else 1,
                "y_sampling": y_samples[idx] if idx < len(y_samples) else 1,
            }
        )
    return channels


def _attributes_from_spec(spec: Any) -> List[Dict[str, Any]]:
    attributes: List[Dict[str, Any]] = []
    for attr in spec.extra_attribs:
        attributes.append(
            {
                "name": attr.name,
                "type": _type_desc_to_str(attr.type),
                "value": _serialize_value(attr.value),
            }
        )
    return attributes


def _get_attr(spec: Any, name: str) -> Any:
    try:
        return spec.getattribute(name)
    except Exception:
        return None


def _type_desc_to_str(type_desc: Any) -> str:
    try:
        return str(type_desc).upper()
    except Exception:
        return "UNKNOWN"


def _serialize_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, bytes):
        return {
            "encoding": "base64",
            "data": base64.b64encode(value).decode("ascii"),
        }
    normalized = _serialize_oiio_type(value)
    if normalized is not None:
        return normalized
    if isinstance(value, (list, tuple)):
        return [_serialize_value(item) for item in value]
    if isinstance(value, dict):
        return {key: _serialize_value(val) for key, val in value.items()}
    return value


def _serialize_oiio_type(value: Any) -> Optional[Any]:
    if hasattr(value, "tolist"):
        try:
            return value.tolist()
        except Exception:
            return None

    if hasattr(value, "min") and hasattr(value, "max"):
        try:
            return {
                "min": _serialize_value(value.min),
                "max": _serialize_value(value.max),
            }
        except Exception:
            return None

    vector_keys = ("x", "y", "z", "w")
    if any(hasattr(value, key) for key in vector_keys):
        vector: Dict[str, Any] = {}
        for key in vector_keys:
            if hasattr(value, key):
                vector[key] = _serialize_value(getattr(value, key))
        if vector:
            return vector

    color_keys = ("r", "g", "b", "a")
    if any(hasattr(value, key) for key in color_keys):
        color: Dict[str, Any] = {}
        for key in color_keys:
            if hasattr(value, key):
                color[key] = _serialize_value(getattr(value, key))
        if color:
            return color

    if hasattr(value, "__iter__") and not isinstance(value, (str, bytes)):
        try:
            return [_serialize_value(item) for item in value]
        except Exception:
            return None

    return None


def _stats_placeholder(enable_deep_stats: bool) -> Dict[str, Any]:
    if enable_deep_stats:
        return {"status": "skipped", "reason": "deep stats not implemented"}
    return {"status": "skipped", "reason": "stats not implemented"}


def _validation_placeholder() -> Dict[str, Any]:
    return {"status": "skipped", "reason": "validation not implemented"}




def _isoformat(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat()


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    return False


def _error_result(message: str) -> Dict[str, Any]:
    return {
        "schema_version": 1,
        "file": {},
        "parts": [],
        "channels": [],
        "attributes": {},
        "stats": {},
        "validation": {},
        "errors": [message],
        "timestamp": _isoformat(time.time()),
    }
