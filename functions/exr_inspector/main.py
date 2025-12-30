"""VAST DataEngine handler for exr-inspector."""

from __future__ import annotations

import base64
import json
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

try:
    import OpenImageIO as oiio
except ImportError:  # pragma: no cover - runtime dependency
    oiio = None


@dataclass
class InspectorConfig:
    enable_meta: bool = True
    enable_stats: bool = False
    enable_deep_stats: bool = False
    enable_validate: bool = False
    policy_path: Optional[str] = None
    schema_version: int = 1


def init(ctx: Any) -> None:
    """Optional initialization hook for DataEngine runtime."""
    _ = ctx


def handler(ctx: Any, event: Dict[str, Any]) -> Dict[str, Any]:
    """Primary DataEngine function handler."""
    _ = ctx
    config = _parse_config(event)

    file_path = _extract_file_path(event)
    if not file_path:
        return _error_result("Missing file path in event payload")

    result: Dict[str, Any] = {
        "schema_version": config.schema_version,
        "file": {},
        "parts": [],
        "channels": [],
        "attributes": {},
        "stats": {},
        "validation": {},
        "errors": [],
    }

    if config.enable_meta:
        result["file"] = _collect_file_info(file_path)
        exr_meta = _inspect_exr(file_path)
        result["file"].update(exr_meta.get("file", {}))
        result["parts"] = exr_meta.get("parts", [])
        result["channels"] = exr_meta.get("channels", [])
        result["attributes"] = exr_meta.get("attributes", {})
        result["errors"].extend(exr_meta.get("errors", []))

    if config.enable_stats:
        result["stats"] = _stats_placeholder(config.enable_deep_stats)

    if config.enable_validate:
        result["validation"] = _validation_placeholder()

    _persist_to_vast_database(result, event)
    return result


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


def _extract_file_path(event: Dict[str, Any]) -> Optional[str]:
    data = event.get("data", {}) if isinstance(event, dict) else {}
    for key in ("path", "file", "file_path"):
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return None


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
    channels: List[Dict[str, Any]] = []
    for idx, name in enumerate(spec.channelnames):
        if channel_formats:
            data_type = _type_desc_to_str(channel_formats[idx])
        else:
            data_type = _type_desc_to_str(spec.format)
        channels.append(
            {
                "part_index": part_index,
                "name": name,
                "type": data_type,
                "x_sampling": spec.x_channel_samples[idx],
                "y_sampling": spec.y_channel_samples[idx],
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
        return str(type_desc)
    except Exception:
        return "unknown"


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


def _persist_to_vast_database(payload: Dict[str, Any], event: Dict[str, Any]) -> None:
    """Placeholder for VAST DataBase persistence."""
    _ = event
    if not _vast_db_configured():
        return

    # TODO: Implement using VAST DataBase client or supported protocol.
    # For now, emit a single-line JSON to stdout for pipeline capture.
    print(json.dumps({"type": "vastdb_upsert", "payload": payload}))


def _vast_db_configured() -> bool:
    required = ["VAST_DB_HOST", "VAST_DB_USER", "VAST_DB_PASSWORD", "VAST_DB_NAME"]
    return all(os.environ.get(key) for key in required)


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
