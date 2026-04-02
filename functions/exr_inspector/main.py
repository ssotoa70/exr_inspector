"""VAST DataEngine handler for exr-inspector.

Triggered by Element.ObjectCreated events on a VAST S3 bucket. Downloads EXR
files via boto3 (S3 credentials from environment variables), extracts metadata
with OpenImageIO, and persists results to VAST DataBase.

Event flow:
  ElementTrigger -> VastEvent with elementpath -> bucket/object_key
  S3 credentials -> environment variables (S3_ENDPOINT, S3_ACCESS_KEY, S3_SECRET_KEY)
  S3 client -> initialized once in init(), reused for all requests
"""

from __future__ import annotations

import base64
import json
import os
import re
import tempfile
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

__version__ = "1.2.0"

try:
    import OpenImageIO as oiio
except ImportError:  # pragma: no cover - runtime dependency
    oiio = None

try:
    import boto3
    from botocore.exceptions import ClientError
except ImportError:  # pragma: no cover - runtime dependency
    boto3 = None
    ClientError = Exception

from vast_db_persistence import persist_to_vast_database

SUPPORTED_EXTENSIONS = {".exr"}

# Global S3 client — initialized once in init(), reused for all requests
s3_client = None


def init(ctx):
    """One-time initialization when the function container starts.

    Sets up the S3 client with credentials from environment variables
    (set via pipeline config). This client is reused for all requests.
    """
    global s3_client

    ctx.logger.info("=" * 80)
    ctx.logger.info("INITIALIZING EXR-INSPECTOR %s", __version__)
    ctx.logger.info("=" * 80)

    s3_endpoint = os.environ.get("S3_ENDPOINT", "")
    s3_access_key = os.environ.get("S3_ACCESS_KEY", "")
    s3_secret_key = os.environ.get("S3_SECRET_KEY", "")

    ctx.logger.info("S3_ENDPOINT: %s", s3_endpoint or "(NOT SET)")
    ctx.logger.info("S3_ACCESS_KEY: %s...%s (len=%d)",
                     s3_access_key[:4], s3_access_key[-4:] if len(s3_access_key) > 8 else "***",
                     len(s3_access_key))

    if not s3_endpoint or not s3_access_key or not s3_secret_key:
        ctx.logger.warning("S3 credentials incomplete - S3 operations will fail")

    if boto3 is not None:
        s3_client = boto3.client(
            "s3",
            endpoint_url=s3_endpoint,
            aws_access_key_id=s3_access_key,
            aws_secret_access_key=s3_secret_key,
        )
        ctx.logger.info("S3 client created successfully")
    else:
        ctx.logger.error("boto3 not available")

    ctx.logger.info("OpenImageIO: %s", "available" if oiio else "NOT AVAILABLE")
    ctx.logger.info("EXR-INSPECTOR initialized successfully")
    ctx.logger.info("=" * 80)


def handler(ctx, event):
    """Primary DataEngine function handler.

    Receives VastEvent objects from DataEngine element triggers.
    For Element events, extracts bucket/key from the elementpath extension.
    Downloads the EXR file via the global S3 client, inspects it with
    OpenImageIO, and persists metadata to VAST DataBase.

    Args:
        ctx: VAST function context with logger
        event: VastEvent object (ElementTriggerVastEvent, etc.)
    """
    ctx.logger.info("=" * 80)
    ctx.logger.info("Processing new EXR inspection request")

    # Log event metadata
    ctx.logger.info("Event ID: %s", event.id)
    ctx.logger.info("Event Type: %s", event.type)
    ctx.logger.info("Event Subtype: %s", event.subtype if event.subtype else "None")

    # Extract file location from event
    s3_bucket = None
    s3_key = None

    if event.type == "Element":
        try:
            element_event = event.as_element_event()
            s3_bucket = element_event.bucket
            s3_key = element_event.object_key

            ctx.logger.info("Element event - Trigger: %s, ID: %s",
                            event.trigger, event.trigger_id)
            ctx.logger.info("Element path: %s",
                            element_event.extensions.get("elementpath"))
            ctx.logger.info("Bucket: %s, Key: %s", s3_bucket, s3_key)
        except Exception as exc:
            ctx.logger.warning("Failed to extract Element properties: %s", exc)

    # Fallback: check data payload
    if not s3_bucket or not s3_key:
        event_data = event.get_data() if hasattr(event, "get_data") else {}
        ctx.logger.info("Using data payload: %s", json.dumps(event_data, indent=2))
        s3_bucket = event_data.get("s3_bucket")
        s3_key = event_data.get("s3_key")

    if not s3_bucket or not s3_key:
        ctx.logger.error("Missing S3 bucket/key in event")
        return _error_result("Missing S3 bucket/key - cannot locate EXR file")

    # Validate extension
    if not _is_supported_extension(s3_key):
        ctx.logger.info("Skipping non-EXR file: %s", s3_key)
        return _error_result(f"Unsupported file extension: {s3_key}")

    # Fetch EXR header from S3 (range GET — only 256KB, not the full file)
    local_path = None
    try:
        local_path, s3_file_info = _fetch_header_from_s3(ctx, s3_bucket, s3_key)

        result: Dict[str, Any] = {
            "schema_version": 1,
            "file": {},
            "parts": [],
            "channels": [],
            "attributes": {},
            "stats": {},
            "validation": {},
            "errors": [],
        }

        # File info from S3 metadata (not local stat)
        result["file"] = {
            "path": s3_key,
            "s3_key": s3_key,
            "s3_bucket": s3_bucket,
            "size_bytes": s3_file_info["size_bytes"],
            "mtime": s3_file_info["mtime"],
            "frame_number": _parse_frame_number(s3_key),
        }

        # Inspect EXR headers from the 256KB temp file
        exr_meta = _inspect_exr(local_path)
        result["file"].update(exr_meta.get("file", {}))
        result["parts"] = exr_meta.get("parts", [])
        result["channels"] = exr_meta.get("channels", [])
        result["attributes"] = exr_meta.get("attributes", {})
        result["errors"].extend(exr_meta.get("errors", []))

        # Persist to VAST DataBase
        persistence_result = persist_to_vast_database(result, ctx=ctx)
        result["persistence"] = persistence_result

        ctx.logger.info("=" * 80)
        ctx.logger.info("EXR INSPECTION RESULTS:")
        ctx.logger.info("  File: s3://%s/%s (%d bytes)", s3_bucket, s3_key, s3_file_info["size_bytes"])
        ctx.logger.info("  Parts: %d", len(result["parts"]))
        ctx.logger.info("  Channels: %d", len(result["channels"]))
        ctx.logger.info("  Errors: %d", len(result["errors"]))
        ctx.logger.info("  Persistence: %s", result.get("persistence", {}).get("status"))
        ctx.logger.info("=" * 80)

        return result

    except Exception as exc:
        ctx.logger.error("EXR inspection failed: %s", exc)
        ctx.logger.exception(exc)
        return _error_result(f"Inspection failed: {exc}")

    finally:
        if local_path and os.path.exists(local_path):
            os.unlink(local_path)


_FRAME_NUMBER_RE = re.compile(r'\.(\d{3,8})\.exr$', re.IGNORECASE)


def _parse_frame_number(s3_key: str) -> Optional[int]:
    """Extract frame number from filename pattern like beauty.0001.exr."""
    match = _FRAME_NUMBER_RE.search(s3_key)
    if match:
        return int(match.group(1))
    return None


def _is_supported_extension(object_key: str) -> bool:
    """Check if the S3 object key has a supported file extension."""
    ext = os.path.splitext(object_key)[1].lower()
    return ext in SUPPORTED_EXTENSIONS


# EXR headers are typically 1-50KB. 256KB provides generous headroom for
# deep multipart files with many attributes. This avoids downloading the
# full file (which can be 10MB-2GB) just to read header metadata.
HEADER_RANGE_BYTES = 256 * 1024  # 256KB


def _fetch_header_from_s3(ctx: Any, bucket: str, key: str) -> tuple:
    """Fetch EXR header bytes and file metadata from S3 using a range GET.

    Returns (local_path, file_info_dict) where local_path is a temp file
    containing the header bytes, and file_info_dict has size_bytes from S3.

    Only reads the first 256KB — all EXR metadata lives in the header.
    No pixel data is transferred. Ephemeral disk usage is ~256KB per request.
    """
    if s3_client is None:
        raise RuntimeError("S3 client not initialized - check init() and env vars")

    # HEAD request to get full file size and metadata
    ctx.logger.info("HEAD s3://%s/%s", bucket, key)
    head = s3_client.head_object(Bucket=bucket, Key=key)
    full_size = head.get("ContentLength", 0)
    last_modified = head.get("LastModified")

    # Range GET: only the first 256KB (the header)
    range_end = min(HEADER_RANGE_BYTES - 1, full_size - 1) if full_size > 0 else HEADER_RANGE_BYTES - 1
    ctx.logger.info("Range GET s3://%s/%s bytes=0-%d (full size: %d)",
                     bucket, key, range_end, full_size)

    response = s3_client.get_object(
        Bucket=bucket, Key=key,
        Range=f"bytes=0-{range_end}",
    )
    header_bytes = response["Body"].read()
    ctx.logger.info("Fetched %d header bytes", len(header_bytes))

    # Write header to a small temp file (OIIO needs a file path)
    tmp = tempfile.NamedTemporaryFile(suffix=".exr", delete=False)
    try:
        tmp.write(header_bytes)
        tmp.flush()
        tmp.close()
    except Exception:
        os.unlink(tmp.name)
        raise

    file_info = {
        "size_bytes": full_size,
        "mtime": _isoformat(last_modified.timestamp()) if last_modified else "",
    }

    return tmp.name, file_info



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
    # Extract raw windows for JSON serialization
    data_window_raw = _get_attr(spec, "dataWindow")
    display_window_raw = _get_attr(spec, "displayWindow")

    # Compute derived integer dimensions from windows
    dw = _extract_window_ints(data_window_raw)
    disp = _extract_window_ints(display_window_raw)

    part: Dict[str, Any] = {
        "part_index": index,
        "width": spec.width,
        "height": spec.height,
        "display_width": (disp["max_x"] - disp["min_x"] + 1) if disp else spec.width,
        "display_height": (disp["max_y"] - disp["min_y"] + 1) if disp else spec.height,
        "data_x_offset": dw["min_x"] if dw else 0,
        "data_y_offset": dw["min_y"] if dw else 0,
        "part_name": _get_attr(spec, "name"),
        "view_name": _get_attr(spec, "view"),
        "multi_view": _get_attr(spec, "multiView"),
        "data_window": _serialize_value(data_window_raw),
        "display_window": _serialize_value(display_window_raw),
        "pixel_aspect_ratio": _get_attr(spec, "pixelAspectRatio"),
        "line_order": _get_attr(spec, "lineOrder"),
        "compression": _get_attr(spec, "compression"),
        "color_space": _get_attr(spec, "oiio:ColorSpace") or _get_attr(spec, "colorspace"),
        "render_software": _get_attr(spec, "software"),
        "is_tiled": bool(spec.tile_width),
        "tile_width": spec.tile_width or None,
        "tile_height": spec.tile_height or None,
        "tile_depth": spec.tile_depth or None,
        "is_deep": bool(spec.deep),
    }
    return {key: value for key, value in part.items() if value is not None}


def _extract_window_ints(window: Any) -> Optional[Dict[str, int]]:
    """Extract integer coordinates from an OIIO window/box object."""
    if window is None:
        return None
    try:
        # OIIO Box2i has .min and .max with .x and .y
        if hasattr(window, "min") and hasattr(window, "max"):
            return {
                "min_x": int(window.min.x) if hasattr(window.min, "x") else int(window.min[0]),
                "min_y": int(window.min.y) if hasattr(window.min, "y") else int(window.min[1]),
                "max_x": int(window.max.x) if hasattr(window.max, "x") else int(window.max[0]),
                "max_y": int(window.max.y) if hasattr(window.max, "y") else int(window.max[1]),
            }
        # Serialized dict format {"min": {"x": 0, "y": 0}, "max": {...}}
        if isinstance(window, dict):
            mn = window.get("min", {})
            mx = window.get("max", {})
            return {
                "min_x": int(mn.get("x", 0)),
                "min_y": int(mn.get("y", 0)),
                "max_x": int(mx.get("x", 0)),
                "max_y": int(mx.get("y", 0)),
            }
    except (TypeError, ValueError, AttributeError):
        pass
    return None


def _spec_to_channels(spec: Any, part_index: int) -> List[Dict[str, Any]]:
    channel_formats = getattr(spec, "channelformats", None) or []
    # OIIO 3.x removed x_channel_samples/y_channel_samples; default to 1
    x_samples = getattr(spec, "x_channel_samples", None) or []
    y_samples = getattr(spec, "y_channel_samples", None) or []
    channels: List[Dict[str, Any]] = []
    for idx, name in enumerate(spec.channelnames):
        if channel_formats and idx < len(channel_formats):
            data_type = _type_desc_to_str(channel_formats[idx])
        else:
            data_type = _type_desc_to_str(spec.format)
        # Split channel name into layer and component (e.g., "beauty.R" -> "beauty", "R")
        if "." in name:
            layer_name = name.rsplit(".", 1)[0]
            component_name = name.rsplit(".", 1)[1]
        else:
            layer_name = ""
            component_name = name

        channels.append(
            {
                "part_index": part_index,
                "name": name,
                "layer_name": layer_name,
                "component_name": component_name,
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





def _isoformat(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat()



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
