"""VAST DataBase persistence layer for exr-inspector with vector embeddings.

This module provides production-ready integration with VAST DataBase for storing
EXR metadata and inspection results. Key features:

- Deterministic vector embeddings for metadata and channel structure
- Idempotent upsert pattern using SELECT-then-INSERT (no UPDATE row IDs)
- PyArrow table conversion for efficient batch inserts
- Transaction-based consistency with rollback on error
- Stateless session management for serverless environments
- Comprehensive error handling and audit logging

Author: Claude Code
Date: 2025-02-05
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import struct
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

try:
    import pyarrow as pa
except ImportError:
    pa = None

try:
    from vastdb_sdk import Session, TableClient
except ImportError:
    Session = None
    TableClient = None


logger = logging.getLogger(__name__)


# Configuration defaults
DEFAULT_METADATA_EMBEDDING_DIM = 384
DEFAULT_CHANNEL_FINGERPRINT_DIM = 128
DEFAULT_SCHEMA_NAME = "exr_metadata"
DEFAULT_VASTDB_ENDPOINT = os.environ.get("VAST_DB_ENDPOINT", "")
DEFAULT_VASTDB_REGION = os.environ.get("VAST_DB_REGION", "us-east-1")


class VectorEmbeddingError(Exception):
    """Raised when vector embedding computation fails."""
    pass


class VASTDatabaseError(Exception):
    """Raised when VAST DataBase operations fail."""
    pass


# ============================================================================
# Vector Embedding Functions
# ============================================================================


def compute_metadata_embedding(
    payload: Dict[str, Any],
    embedding_dim: int = DEFAULT_METADATA_EMBEDDING_DIM,
) -> List[float]:
    """
    Compute a deterministic vector embedding for complete EXR metadata.

    This function creates a single normalized vector representing all metadata
    from an EXR file inspection. The embedding is deterministic: the same input
    payload will always produce the same vector. This approach avoids external
    ML dependencies while capturing structural metadata characteristics.

    The embedding is computed by:
    1. Extracting key features (channel count, compression type, etc.)
    2. Creating a normalized feature vector
    3. Hashing to fill additional dimensions
    4. Normalizing to unit vector

    Args:
        payload: Complete exr-inspector JSON output from _inspect_exr()
        embedding_dim: Output vector dimensionality (default: 384)

    Returns:
        List of float values with length equal to embedding_dim

    Raises:
        VectorEmbeddingError: If payload structure is invalid

    Example:
        >>> payload = {
        ...     "file": {"multipart_count": 2, "is_deep": False},
        ...     "channels": [...],
        ...     "parts": [...]
        ... }
        >>> vec = compute_metadata_embedding(payload)
        >>> len(vec)  # == 384
        384
        >>> # Same payload produces same vector (deterministic)
        >>> vec2 = compute_metadata_embedding(payload)
        >>> all(abs(v1 - v2) < 1e-9 for v1, v2 in zip(vec, vec2))
        True
    """
    try:
        # Extract normalized features from payload
        features = _extract_metadata_features(payload)

        # Build initial feature vector from extracted metrics
        feature_values = [
            float(features.get("channel_count", 0)) / max(1, 64),  # normalize to [0,1]
            float(features.get("part_count", 0)) / max(1, 16),
            float(features.get("is_deep", 0)),
            float(features.get("is_tiled", 0)),
            float(features.get("has_multiview", 0)),
            _compression_to_normalized(features.get("compression_type", "")),
        ]

        # Hash the complete payload JSON to fill remaining dimensions
        payload_hash = hashlib.sha256(
            json.dumps(payload, sort_keys=True, default=str).encode()
        ).digest()

        # Convert hash bytes to normalized float values
        hash_values = [
            (struct.unpack("f", payload_hash[i : i + 4])[0] % 1.0)
            if i + 4 <= len(payload_hash)
            else 0.0
            for i in range(0, len(payload_hash) - 4, 4)
        ]

        # Combine feature and hash vectors
        combined = feature_values + hash_values

        # Pad or truncate to target dimension
        if len(combined) < embedding_dim:
            # Pad with derived values from combined
            while len(combined) < embedding_dim:
                seed = len(combined)
                combined.append(
                    abs(
                        (sum(combined) * (seed + 1))
                        % (seed + 2)
                    ) / max(1, seed + 2)
                )
        else:
            combined = combined[:embedding_dim]

        # Normalize to unit vector (L2 norm)
        magnitude = (sum(v * v for v in combined) ** 0.5)
        if magnitude < 1e-9:
            # Degenerate case: uniform vector
            return [1.0 / (embedding_dim ** 0.5)] * embedding_dim

        normalized = [v / magnitude for v in combined]
        return normalized

    except Exception as exc:
        raise VectorEmbeddingError(
            f"Failed to compute metadata embedding: {exc}"
        ) from exc


def compute_channel_fingerprint(
    channels: List[Dict[str, Any]],
    embedding_dim: int = DEFAULT_CHANNEL_FINGERPRINT_DIM,
) -> List[float]:
    """
    Compute a deterministic vector embedding for EXR channel structure.

    This function creates a fingerprint of the channel layout and properties.
    Useful for finding files with similar channel configurations.

    The fingerprint captures:
    - Channel count and naming patterns
    - Data types distribution
    - Sampling patterns (x/y sampling ratios)
    - Layer/component organization

    Args:
        channels: List of channel dictionaries from exr-inspector output
        embedding_dim: Output vector dimensionality (default: 128)

    Returns:
        List of float values with length equal to embedding_dim

    Raises:
        VectorEmbeddingError: If channel structure is invalid

    Example:
        >>> channels = [
        ...     {"name": "R", "type": "float", "x_sampling": 1, "y_sampling": 1},
        ...     {"name": "G", "type": "float", "x_sampling": 1, "y_sampling": 1},
        ... ]
        >>> fp = compute_channel_fingerprint(channels)
        >>> len(fp)  # == 128
        128
    """
    try:
        if not channels:
            return [0.0] * embedding_dim

        # Extract channel features
        channel_count = len(channels)
        type_counts: Dict[str, int] = {}
        total_x_sampling = 0
        total_y_sampling = 0
        layer_set = set()

        for ch in channels:
            ch_type = ch.get("type", "unknown")
            type_counts[ch_type] = type_counts.get(ch_type, 0) + 1
            total_x_sampling += ch.get("x_sampling", 1)
            total_y_sampling += ch.get("y_sampling", 1)

            # Extract layer name (e.g., "diffuse.R" -> "diffuse")
            name = ch.get("name", "")
            if "." in name:
                layer_set.add(name.split(".")[0])

        # Build feature vector
        features = [
            float(channel_count) / 64.0,  # normalize to [0,1]
            float(len(layer_set)) / max(1, channel_count),
            float(total_x_sampling) / max(1, channel_count * 2),
            float(total_y_sampling) / max(1, channel_count * 2),
        ]

        # Add type distribution as ratios
        for data_type in ["float", "half", "uint32", "uint8"]:
            count = type_counts.get(data_type, 0)
            features.append(float(count) / max(1, channel_count))

        # Hash channel names for unique identification
        channel_names = [ch.get("name", "") for ch in channels]
        names_hash = hashlib.md5(
            "|".join(channel_names).encode()
        ).digest()

        hash_values = [
            (struct.unpack("f", names_hash[i : i + 4])[0] % 1.0)
            if i + 4 <= len(names_hash)
            else 0.0
            for i in range(0, len(names_hash) - 4, 4)
        ]

        # Combine all vectors
        combined = features + hash_values

        # Pad or truncate
        if len(combined) < embedding_dim:
            while len(combined) < embedding_dim:
                combined.append(
                    abs(
                        sum(combined[:4])
                        * (len(combined) + 1)
                    ) % 1.0
                )
        else:
            combined = combined[:embedding_dim]

        # Normalize to unit vector
        magnitude = (sum(v * v for v in combined) ** 0.5)
        if magnitude < 1e-9:
            return [1.0 / (embedding_dim ** 0.5)] * embedding_dim

        return [v / magnitude for v in combined]

    except Exception as exc:
        raise VectorEmbeddingError(
            f"Failed to compute channel fingerprint: {exc}"
        ) from exc


# ============================================================================
# Helper Functions for Vector Computation
# ============================================================================


def _extract_metadata_features(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Extract key features from EXR inspection payload."""
    file_info = payload.get("file", {})
    channels = payload.get("channels", [])
    parts = payload.get("parts", [])

    # Count unique compressions
    compressions = set()
    for part in parts:
        if comp := part.get("compression"):
            compressions.add(comp)

    return {
        "channel_count": len(channels),
        "part_count": len(parts),
        "is_deep": bool(file_info.get("is_deep", False)),
        "is_tiled": any(p.get("is_tiled", False) for p in parts),
        "has_multiview": any(p.get("multi_view") for p in parts),
        "compression_type": list(compressions)[0] if compressions else "none",
    }


def _compression_to_normalized(compression_type: str) -> float:
    """Convert compression type string to normalized float [0, 1]."""
    compression_map = {
        "none": 0.0,
        "rle": 0.2,
        "zips": 0.4,
        "zip": 0.5,
        "piz": 0.6,
        "pxr24": 0.7,
        "b44": 0.8,
        "b44a": 0.85,
        "dwaa": 0.9,
        "dwab": 0.95,
    }
    return compression_map.get(compression_type.lower(), 0.5)


# ============================================================================
# PyArrow Conversion Functions
# ============================================================================


def payload_to_files_row(
    payload: Dict[str, Any],
    metadata_embedding: List[float],
    file_id: Optional[str] = None,
) -> pa.Table:
    """
    Convert inspection payload to a PyArrow table row for files table.

    Creates a single-row table with file-level metadata including embedded vector.

    Args:
        payload: exr-inspector JSON output
        metadata_embedding: Vector from compute_metadata_embedding()
        file_id: Optional UUID (generated if not provided)

    Returns:
        PyArrow Table with schema matching VAST DataBase files table

    Raises:
        ValueError: If payload structure is invalid
    """
    if pa is None:
        raise ImportError("pyarrow is required for payload conversion")

    file_info = payload.get("file", {})
    if not file_info.get("path"):
        raise ValueError("Payload missing file.path")

    # Generate file_id if not provided
    if not file_id:
        path_hash = hashlib.md5(file_info["path"].encode()).hexdigest()
        mtime = file_info.get("mtime", "")
        file_id = hashlib.sha256(
            f"{file_info['path']}{mtime}{path_hash}".encode()
        ).hexdigest()[:16]

    # Create normalized path for deduplication
    file_path_normalized = _normalize_path(file_info["path"])

    # Compute header hash from key structural elements
    header_elements = [
        str(file_info.get("multipart_count", 0)),
        str(file_info.get("is_deep", False)),
        json.dumps(payload.get("parts", []), sort_keys=True, default=str),
    ]
    header_hash = hashlib.sha256(
        "".join(header_elements).encode()
    ).hexdigest()

    now = datetime.now(timezone.utc).isoformat()

    schema = pa.schema([
        ("file_id", pa.string()),
        ("file_path", pa.string()),
        ("file_path_normalized", pa.string()),
        ("header_hash", pa.string()),
        ("size_bytes", pa.int64()),
        ("mtime", pa.string()),
        ("multipart_count", pa.int32()),
        ("is_deep", pa.bool_()),
        ("metadata_embedding", pa.list_(pa.float32())),
        ("inspection_timestamp", pa.string()),
        ("inspection_count", pa.int32()),
        ("last_inspected", pa.string()),
    ])

    data = {
        "file_id": [file_id],
        "file_path": [file_info.get("path", "")],
        "file_path_normalized": [file_path_normalized],
        "header_hash": [header_hash],
        "size_bytes": [file_info.get("size_bytes", 0)],
        "mtime": [file_info.get("mtime", "")],
        "multipart_count": [file_info.get("multipart_count", 0)],
        "is_deep": [file_info.get("is_deep", False)],
        "metadata_embedding": [metadata_embedding],
        "inspection_timestamp": [now],
        "inspection_count": [1],
        "last_inspected": [now],
    }

    return pa.table(data, schema=schema)


def payload_to_parts_rows(
    payload: Dict[str, Any],
    file_id: str,
) -> pa.Table:
    """
    Convert inspection payload to PyArrow table rows for parts table.

    Creates one row per part (subimage) in the EXR file.

    Args:
        payload: exr-inspector JSON output
        file_id: Parent file_id from files table

    Returns:
        PyArrow Table with schema matching VAST DataBase parts table
    """
    if pa is None:
        raise ImportError("pyarrow is required for payload conversion")

    parts = payload.get("parts", [])
    if not parts:
        return pa.table({
            "file_id": pa.array([], type=pa.string()),
        })

    file_info = payload.get("file", {})
    file_path = file_info.get("path", "")

    schema = pa.schema([
        ("file_id", pa.string()),
        ("file_path", pa.string()),
        ("part_index", pa.int32()),
        ("part_name", pa.string()),
        ("view_name", pa.string()),
        ("multi_view", pa.bool_()),
        ("data_window", pa.string()),  # JSON serialized
        ("display_window", pa.string()),  # JSON serialized
        ("pixel_aspect_ratio", pa.float32()),
        ("line_order", pa.string()),
        ("compression", pa.string()),
        ("is_tiled", pa.bool_()),
        ("tile_width", pa.int32()),
        ("tile_height", pa.int32()),
        ("tile_depth", pa.int32()),
        ("is_deep", pa.bool_()),
    ])

    data = {
        "file_id": [],
        "file_path": [],
        "part_index": [],
        "part_name": [],
        "view_name": [],
        "multi_view": [],
        "data_window": [],
        "display_window": [],
        "pixel_aspect_ratio": [],
        "line_order": [],
        "compression": [],
        "is_tiled": [],
        "tile_width": [],
        "tile_height": [],
        "tile_depth": [],
        "is_deep": [],
    }

    for part in parts:
        data["file_id"].append(file_id)
        data["file_path"].append(file_path)
        data["part_index"].append(part.get("part_index", 0))
        data["part_name"].append(part.get("part_name"))
        data["view_name"].append(part.get("view_name"))
        data["multi_view"].append(bool(part.get("multi_view")))
        data["data_window"].append(json.dumps(part.get("data_window")))
        data["display_window"].append(json.dumps(part.get("display_window")))
        data["pixel_aspect_ratio"].append(
            float(part.get("pixel_aspect_ratio", 1.0))
        )
        data["line_order"].append(part.get("line_order"))
        data["compression"].append(part.get("compression"))
        data["is_tiled"].append(bool(part.get("is_tiled")))
        data["tile_width"].append(part.get("tile_width") or 0)
        data["tile_height"].append(part.get("tile_height") or 0)
        data["tile_depth"].append(part.get("tile_depth") or 0)
        data["is_deep"].append(bool(part.get("is_deep")))

    return pa.table(data, schema=schema)


def payload_to_channels_rows(
    payload: Dict[str, Any],
    file_id: str,
    channel_fingerprint: List[float],
) -> pa.Table:
    """
    Convert inspection payload to PyArrow table rows for channels table.

    Creates one row per channel across all parts.

    Args:
        payload: exr-inspector JSON output
        file_id: Parent file_id from files table
        channel_fingerprint: Vector from compute_channel_fingerprint()

    Returns:
        PyArrow Table with schema matching VAST DataBase channels table
    """
    if pa is None:
        raise ImportError("pyarrow is required for payload conversion")

    channels = payload.get("channels", [])
    if not channels:
        return pa.table({
            "file_id": pa.array([], type=pa.string()),
        })

    file_info = payload.get("file", {})
    file_path = file_info.get("path", "")

    schema = pa.schema([
        ("file_id", pa.string()),
        ("file_path", pa.string()),
        ("part_index", pa.int32()),
        ("channel_name", pa.string()),
        ("channel_type", pa.string()),
        ("x_sampling", pa.int32()),
        ("y_sampling", pa.int32()),
        ("channel_fingerprint", pa.list_(pa.float32())),
    ])

    data = {
        "file_id": [],
        "file_path": [],
        "part_index": [],
        "channel_name": [],
        "channel_type": [],
        "x_sampling": [],
        "y_sampling": [],
        "channel_fingerprint": [],
    }

    for idx, channel in enumerate(channels):
        data["file_id"].append(file_id)
        data["file_path"].append(file_path)
        data["part_index"].append(channel.get("part_index", 0))
        data["channel_name"].append(channel.get("name", ""))
        data["channel_type"].append(channel.get("type", ""))
        data["x_sampling"].append(channel.get("x_sampling", 1))
        data["y_sampling"].append(channel.get("y_sampling", 1))
        # Include fingerprint only in first row to avoid duplication
        data["channel_fingerprint"].append(
            channel_fingerprint if idx == 0 else []
        )

    return pa.table(data, schema=schema)


def payload_to_attributes_rows(
    payload: Dict[str, Any],
    file_id: str,
) -> pa.Table:
    """
    Convert inspection payload to PyArrow table rows for attributes table.

    Creates one row per attribute across all parts.

    Args:
        payload: exr-inspector JSON output
        file_id: Parent file_id from files table

    Returns:
        PyArrow Table with schema matching VAST DataBase attributes table
    """
    if pa is None:
        raise ImportError("pyarrow is required for payload conversion")

    attributes_data = payload.get("attributes", {})
    parts_attrs = attributes_data.get("parts", [])

    if not parts_attrs:
        return pa.table({
            "file_id": pa.array([], type=pa.string()),
        })

    file_info = payload.get("file", {})
    file_path = file_info.get("path", "")

    schema = pa.schema([
        ("file_id", pa.string()),
        ("file_path", pa.string()),
        ("part_index", pa.int32()),
        ("attribute_name", pa.string()),
        ("attribute_type", pa.string()),
        ("attribute_value", pa.string()),  # JSON serialized
    ])

    data = {
        "file_id": [],
        "file_path": [],
        "part_index": [],
        "attribute_name": [],
        "attribute_type": [],
        "attribute_value": [],
    }

    for part_idx, part_attrs in enumerate(parts_attrs):
        if not isinstance(part_attrs, list):
            continue

        for attr in part_attrs:
            data["file_id"].append(file_id)
            data["file_path"].append(file_path)
            data["part_index"].append(part_idx)
            data["attribute_name"].append(attr.get("name", ""))
            data["attribute_type"].append(attr.get("type", ""))
            data["attribute_value"].append(
                json.dumps(attr.get("value"))
            )

    return pa.table(data, schema=schema)


# ============================================================================
# Path Normalization
# ============================================================================


def _normalize_path(path: str) -> str:
    """
    Normalize file path for consistent deduplication.

    Removes symbolic links, normalizes separators, and converts to lowercase
    for case-insensitive filesystems.

    Args:
        path: File path to normalize

    Returns:
        Normalized path string suitable as unique key
    """
    import pathlib

    try:
        # Resolve to absolute path and remove symlinks
        resolved = str(pathlib.Path(path).resolve())
    except (OSError, RuntimeError):
        # Fall back if path cannot be resolved
        resolved = os.path.abspath(path)

    # Normalize separators to forward slash for consistency
    normalized = resolved.replace(os.sep, "/").lower()
    return normalized


# ============================================================================
# VAST DataBase Session Management
# ============================================================================


def _create_vastdb_session(event: Dict[str, Any]) -> Optional[Any]:
    """
    Create a VAST DataBase session from environment or event context.

    Session creation prioritizes:
    1. Event context (credentials passed from DataEngine)
    2. Environment variables
    3. Default configuration

    Args:
        event: DataEngine event context that may contain VAST credentials

    Returns:
        Session object if successful, None if not configured

    Raises:
        VASTDatabaseError: If session creation fails due to invalid credentials
    """
    if Session is None:
        logger.warning("vastdb_sdk not available; skipping persistence")
        return None

    # Extract credentials from event context or environment
    endpoint = (
        event.get("vastdb_endpoint")
        or os.environ.get("VAST_DB_ENDPOINT")
        or DEFAULT_VASTDB_ENDPOINT
    )
    access_key = (
        event.get("vastdb_access_key")
        or os.environ.get("VAST_DB_ACCESS_KEY")
    )
    secret_key = (
        event.get("vastdb_secret_key")
        or os.environ.get("VAST_DB_SECRET_KEY")
    )
    region = (
        event.get("vastdb_region")
        or os.environ.get("VAST_DB_REGION")
        or DEFAULT_VASTDB_REGION
    )

    if not endpoint:
        logger.debug("VAST_DB_ENDPOINT not configured")
        return None

    try:
        session = Session(
            endpoint=endpoint,
            access_key=access_key,
            secret_key=secret_key,
            region=region,
        )
        logger.info(f"VAST DataBase session created: {endpoint}")
        return session

    except Exception as exc:
        raise VASTDatabaseError(
            f"Failed to create VAST DataBase session: {exc}"
        ) from exc


# ============================================================================
# Main Persistence Function
# ============================================================================


def persist_to_vast_database(
    payload: Dict[str, Any],
    event: Dict[str, Any],
    vastdb_session: Optional[Any] = None,
) -> Dict[str, Any]:
    """
    Persist EXR inspection results to VAST DataBase with idempotent upsert.

    This is the main entry point for VAST DataBase persistence. It orchestrates
    the complete flow:

    1. Create/validate VAST DataBase session
    2. Compute vector embeddings
    3. Convert payload to PyArrow tables
    4. Start transaction
    5. Check existence (SELECT) by file_path_normalized + header_hash
    6. If new: INSERT all related records (files, parts, channels, attributes)
    7. If exists: SKIP INSERT (idempotent) or UPDATE audit fields
    8. Commit transaction with error handling

    Args:
        payload: Complete exr-inspector JSON output from handler()
        event: DataEngine event context (may contain VAST credentials)
        vastdb_session: Optional pre-created session (for testing)

    Returns:
        dict with keys:
            - status: "success" or "error"
            - file_id: Unique identifier for persisted file (if successful)
            - inserted: bool indicating if new record was inserted
            - message: Human-readable status message
            - error: Error message (if status == "error")

    Example:
        >>> payload = {
        ...     "file": {"path": "/data/test.exr", ...},
        ...     "channels": [...],
        ...     ...
        ... }
        >>> result = persist_to_vast_database(payload, event)
        >>> if result["status"] == "success":
        ...     print(f"File ID: {result['file_id']}")
    """
    result: Dict[str, Any] = {
        "status": "error",
        "file_id": None,
        "inserted": False,
        "message": "",
        "error": None,
    }

    # Validate payload structure
    file_info = payload.get("file", {})
    if not file_info.get("path"):
        result["error"] = "Payload missing file.path"
        result["message"] = "Invalid payload structure"
        logger.error(result["error"])
        return result

    file_path = file_info["path"]

    try:
        # Create or use provided session
        session = vastdb_session or _create_vastdb_session(event)
        if session is None:
            result["status"] = "skipped"
            result["message"] = "VAST DataBase not configured"
            logger.debug(f"VAST persistence skipped for {file_path}")
            return result

        # Compute vector embeddings
        logger.debug(f"Computing embeddings for {file_path}")
        metadata_embedding = compute_metadata_embedding(payload)
        channel_fingerprint = compute_channel_fingerprint(
            payload.get("channels", [])
        )

        # Convert payload to PyArrow tables
        files_table = payload_to_files_row(payload, metadata_embedding)
        file_id = files_table.column("file_id")[0].as_py()

        parts_table = payload_to_parts_rows(payload, file_id)
        channels_table = payload_to_channels_rows(
            payload, file_id, channel_fingerprint
        )
        attributes_table = payload_to_attributes_rows(payload, file_id)

        logger.debug(f"Tables converted for {file_id}: files, parts, channels, attributes")

        # Perform transaction
        _persist_with_transaction(
            session=session,
            file_path=file_path,
            file_id=file_id,
            files_table=files_table,
            parts_table=parts_table,
            channels_table=channels_table,
            attributes_table=attributes_table,
            result=result,
        )

    except VectorEmbeddingError as exc:
        result["error"] = f"Embedding computation failed: {exc}"
        result["message"] = "Vector embedding error"
        logger.error(result["error"])

    except VASTDatabaseError as exc:
        result["error"] = f"VAST DataBase error: {exc}"
        result["message"] = "Database connection error"
        logger.error(result["error"])

    except Exception as exc:
        result["error"] = f"Unexpected error during persistence: {exc}"
        result["message"] = "Persistence failed"
        logger.exception(f"Unhandled exception persisting {file_path}")

    return result


def _persist_with_transaction(
    session: Any,
    file_path: str,
    file_id: str,
    files_table: pa.Table,
    parts_table: pa.Table,
    channels_table: pa.Table,
    attributes_table: pa.Table,
    result: Dict[str, Any],
) -> None:
    """
    Execute idempotent upsert within transaction.

    Uses SELECT-then-INSERT pattern to avoid UPDATE with row IDs (which has
    undocumented behavior in VAST DataBase). The pattern is:

    1. SELECT to check if file exists (by file_path_normalized + header_hash)
    2. If found: Skip insert (idempotent), optionally UPDATE audit fields
    3. If not found: Insert complete record across all tables
    4. Commit transaction; rollback on any error

    Args:
        session: VAST DataBase session
        file_path: File path being persisted
        file_id: Unique file identifier
        files_table: PyArrow table with file metadata
        parts_table: PyArrow table with part records
        channels_table: PyArrow table with channel records
        attributes_table: PyArrow table with attribute records
        result: Result dict to populate with status

    Side Effects:
        Updates result dict with status, file_id, inserted flag, and message
    """
    schema_name = os.environ.get("VAST_DB_SCHEMA", DEFAULT_SCHEMA_NAME)
    txn = None

    try:
        # Start transaction
        txn = session.begin()
        logger.debug(f"Transaction started for {file_id}")

        # Get normalized path and header hash for deduplication
        file_path_normalized = _normalize_path(file_path)
        header_hash = files_table.column("header_hash")[0].as_py()

        # Check if file already exists using SELECT
        files_client = session.table(f"{schema_name}.files")
        existing = _select_existing_file(
            files_client,
            file_path_normalized,
            header_hash,
        )

        if existing:
            # File already exists (idempotent)
            result["status"] = "success"
            result["file_id"] = existing["file_id"]
            result["inserted"] = False
            result["message"] = f"File already persisted: {file_id}"
            logger.info(f"File exists (idempotent): {file_id}")

            # Optionally update last_inspected timestamp
            _update_audit_fields(files_client, file_id)
            txn.commit()

        else:
            # New file: insert across all tables
            _insert_new_file(
                session,
                schema_name,
                file_id,
                files_table,
                parts_table,
                channels_table,
                attributes_table,
            )

            result["status"] = "success"
            result["file_id"] = file_id
            result["inserted"] = True
            result["message"] = f"File persisted: {file_id}"
            logger.info(f"File inserted: {file_id}")

            txn.commit()

    except Exception as exc:
        if txn:
            try:
                txn.rollback()
                logger.debug(f"Transaction rolled back for {file_id}")
            except Exception as rollback_exc:
                logger.warning(f"Rollback failed: {rollback_exc}")

        raise VASTDatabaseError(f"Transaction failed: {exc}") from exc


def _select_existing_file(
    files_client: Any,
    file_path_normalized: str,
    header_hash: str,
) -> Optional[Dict[str, Any]]:
    """
    Query for existing file record by normalized path and header hash.

    Args:
        files_client: Table client for files table
        file_path_normalized: Normalized file path
        header_hash: SHA256 hash of file header structure

    Returns:
        Existing file record dict if found, None otherwise
    """
    try:
        # SELECT with WHERE clause for idempotent key
        query = f"""
            SELECT file_id, file_path, header_hash, last_inspected
            FROM files
            WHERE file_path_normalized = ? AND header_hash = ?
            LIMIT 1
        """
        result = files_client.select(query, [file_path_normalized, header_hash])

        if result and len(result) > 0:
            return result[0]

        return None

    except Exception as exc:
        logger.warning(f"SELECT query failed: {exc}")
        return None


def _update_audit_fields(
    files_client: Any,
    file_id: str,
) -> None:
    """
    Update last_inspected timestamp and increment inspection_count.

    Note: We use a separate UPDATE statement rather than attempting to
    modify the original row ID, as row ID updates have undocumented behavior.

    Args:
        files_client: Table client for files table
        file_id: File identifier

    Side Effects:
        Updates database record (if UPDATE is supported)
    """
    try:
        now = datetime.now(timezone.utc).isoformat()
        update_query = f"""
            UPDATE files
            SET last_inspected = ?, inspection_count = inspection_count + 1
            WHERE file_id = ?
        """
        files_client.update(update_query, [now, file_id])
        logger.debug(f"Audit fields updated for {file_id}")

    except Exception as exc:
        # Audit field update is optional; don't fail transaction
        logger.warning(f"Failed to update audit fields for {file_id}: {exc}")


def _insert_new_file(
    session: Any,
    schema_name: str,
    file_id: str,
    files_table: pa.Table,
    parts_table: pa.Table,
    channels_table: pa.Table,
    attributes_table: pa.Table,
) -> None:
    """
    Insert new file record and related data across all tables.

    Args:
        session: VAST DataBase session
        schema_name: Schema name
        file_id: File identifier
        files_table: File metadata table
        parts_table: Part records table
        channels_table: Channel records table
        attributes_table: Attribute records table

    Raises:
        VASTDatabaseError: If any insert fails
    """
    try:
        # Insert in order: files (parent) -> parts, channels, attributes (children)
        files_client = session.table(f"{schema_name}.files")
        files_client.insert(files_table)
        logger.debug(f"Inserted files record for {file_id}")

        if parts_table.num_rows > 0:
            parts_client = session.table(f"{schema_name}.parts")
            parts_client.insert(parts_table)
            logger.debug(f"Inserted {parts_table.num_rows} part records")

        if channels_table.num_rows > 0:
            channels_client = session.table(f"{schema_name}.channels")
            channels_client.insert(channels_table)
            logger.debug(f"Inserted {channels_table.num_rows} channel records")

        if attributes_table.num_rows > 0:
            attributes_client = session.table(f"{schema_name}.attributes")
            attributes_client.insert(attributes_table)
            logger.debug(f"Inserted {attributes_table.num_rows} attribute records")

    except Exception as exc:
        raise VASTDatabaseError(f"Insert failed for {file_id}: {exc}") from exc
