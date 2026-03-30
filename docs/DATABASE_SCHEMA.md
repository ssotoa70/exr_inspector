# Database Schema Reference

exr-inspector persists metadata to four tables in VAST DataBase. Tables are auto-created on first invocation using the `vastdb` Python SDK with PyArrow schemas.

## Schema Overview

All tables reside in the `exr_metadata` schema (configurable via `VAST_DB_SCHEMA`). The database bucket must be a **Database-enabled view** (created with `S3,DATABASE` protocols).

```
$VAST_DB_BUCKET/
  exr_metadata/
    files        -- one row per EXR file
    parts        -- one row per subimage (part)
    channels     -- one row per channel (AOV)
    attributes   -- one row per header attribute
```

## Tables

### `files`

Root table storing one row per unique EXR file. Contains file-level metadata and a 384-dimensional vector embedding.

| Column | Type | Description |
|--------|------|-------------|
| `file_id` | STRING | SHA256-based unique identifier (primary key) |
| `file_path` | STRING | Original S3 object key |
| `file_path_normalized` | STRING | Lowercased path for deduplication |
| `header_hash` | STRING | SHA256 of EXR header structure |
| `size_bytes` | INT64 | File size in bytes |
| `mtime` | STRING | Modification time (ISO 8601 UTC) |
| `multipart_count` | INT32 | Number of subimages |
| `is_deep` | BOOL | True if any part contains deep data |
| `metadata_embedding` | FLOAT32[384] | Deterministic vector embedding of file structure |
| `frame_number` | INT32 | Frame number parsed from filename (e.g., 1001 from `beauty.1001.exr`). NULL if no frame pattern found. |
| `inspection_timestamp` | STRING | First inspection time (ISO 8601) |
| `inspection_count` | INT32 | Number of inspections |
| `last_inspected` | STRING | Most recent inspection (ISO 8601) |

### `parts`

One row per EXR subimage (part). Multipart EXR files produce multiple rows.

| Column | Type | Description |
|--------|------|-------------|
| `file_id` | STRING | Foreign key to `files` |
| `file_path` | STRING | Denormalized file path |
| `part_index` | INT32 | Zero-based subimage index |
| `width` | INT32 | Data window width in pixels |
| `height` | INT32 | Data window height in pixels |
| `display_width` | INT32 | Display window width in pixels |
| `display_height` | INT32 | Display window height in pixels |
| `data_x_offset` | INT32 | Data window X origin (non-zero = overscan) |
| `data_y_offset` | INT32 | Data window Y origin (non-zero = overscan) |
| `part_name` | STRING | Part name (e.g., `beauty`, `diffuse`) |
| `view_name` | STRING | Stereo view name (e.g., `left`, `right`) |
| `multi_view` | BOOL | True if file declares multiView |
| `data_window` | STRING | JSON bounding box of pixel data region |
| `display_window` | STRING | JSON bounding box of display aperture |
| `pixel_aspect_ratio` | FLOAT32 | Pixel width/height ratio |
| `line_order` | STRING | `INCREASING_Y`, `DECREASING_Y`, or `RANDOM_Y` |
| `compression` | STRING | `ZIP`, `ZIPS`, `PIZ`, `DWAA`, `DWAB`, `RLE`, `NONE`, etc. |
| `color_space` | STRING | Color space (e.g., `ACES - ACEScg`, `sRGB`, `Linear`). From `oiio:ColorSpace` or `colorspace` attribute. |
| `render_software` | STRING | Software that produced the file (e.g., `Arnold 7.2.1`, `RenderMan 25`). From `software` attribute. |
| `is_tiled` | BOOL | True if tiled storage |
| `tile_width` | INT32 | Tile width in pixels (NULL if scanline) |
| `tile_height` | INT32 | Tile height in pixels |
| `tile_depth` | INT32 | Tile depth (volumetric data) |
| `is_deep` | BOOL | True if this part contains deep data |

### `channels`

One row per channel (AOV) per part. Includes a 128-dimensional fingerprint vector.

| Column | Type | Description |
|--------|------|-------------|
| `file_id` | STRING | Foreign key to `files` |
| `file_path` | STRING | Denormalized file path |
| `part_index` | INT32 | Subimage index |
| `channel_name` | STRING | Full channel name (e.g., `beauty.R`, `Z`, `A`) |
| `layer_name` | STRING | Layer portion of channel name (e.g., `beauty` from `beauty.R`). Empty for flat channels like `R`, `Z`. |
| `component_name` | STRING | Component portion (e.g., `R` from `beauty.R`). For flat channels, same as channel_name. |
| `channel_type` | STRING | `HALF` (16-bit), `FLOAT` (32-bit), `UINT` (32-bit unsigned) |
| `x_sampling` | INT32 | Horizontal subsampling (1 = full res) |
| `y_sampling` | INT32 | Vertical subsampling (1 = full res) |
| `channel_fingerprint` | FLOAT32[128] | Deterministic vector of channel composition |

### `attributes`

One row per EXR header attribute per part. Key-value design with typed value columns.

| Column | Type | Description |
|--------|------|-------------|
| `file_id` | STRING | Foreign key to `files` |
| `file_path` | STRING | Denormalized file path |
| `part_index` | INT32 | Subimage index |
| `attr_name` | STRING | Attribute name (e.g., `chromaticities`, `owner`) |
| `attr_type` | STRING | OpenImageIO type (e.g., `STRING`, `FLOAT`, `V2F`, `MATRIX44`) |
| `value_json` | STRING | JSON-serialized value (complex types) |
| `value_text` | STRING | Plain text value (string attributes) |
| `value_int` | INT64 | Integer value |
| `value_float` | FLOAT64 | Float value |

## Auto-Provisioning

Tables are created automatically on first invocation using a **get-or-create** pattern:

```python
# DDL runs in a separate transaction from inserts
with session.transaction() as tx:
    bucket = tx.bucket(bucket_name)
    schema = _get_or_create_schema(bucket, schema_name)
    for table_name, arrow_schema in TABLE_DEFINITIONS.items():
        _get_or_create_table(schema, table_name, arrow_schema)
```

The `create_schema` and `create_table` calls are NOT idempotent in the vastdb SDK. The get-or-create pattern wraps them in try/except to handle concurrent first-run scenarios safely.

**Note:** The database bucket must pre-exist as a Database-enabled view. The SDK cannot create buckets.

## Trino Query Examples

Connect to Trino and set the default schema:

```sql
USE vast."$DATABASE_BUCKET/exr_metadata";
```

### Find all deep EXR files

```sql
SELECT file_path, size_bytes, multipart_count, last_inspected
FROM files
WHERE is_deep = true
ORDER BY size_bytes DESC;
```

### List all AOV channels for a file

```sql
SELECT c.part_index, c.channel_name, c.channel_type, p.part_name, p.compression
FROM channels c
JOIN parts p ON c.file_id = p.file_id AND c.part_index = p.part_index
WHERE c.file_path = 'renders/shot_001/beauty.1001.exr'
ORDER BY c.part_index, c.channel_name;
```

### Compression usage summary

```sql
SELECT
    p.compression,
    COUNT(DISTINCT p.file_id) AS file_count,
    CAST(SUM(f.size_bytes) AS DOUBLE) / (1024 * 1024 * 1024) AS total_gb
FROM parts p
JOIN files f ON p.file_id = f.file_id
GROUP BY p.compression
ORDER BY file_count DESC;
```

### Find files by software

```sql
SELECT f.file_path, a.value_text AS software
FROM files f
JOIN attributes a ON f.file_id = a.file_id
WHERE a.attr_name = 'software' AND a.value_text LIKE '%Arnold%';
```

### Files with chromaticities metadata

```sql
SELECT f.file_path, a.value_json
FROM files f
JOIN attributes a ON f.file_id = a.file_id
WHERE a.attr_name = 'chromaticities';
```

### Complex multi-layer renders (>20 channels)

```sql
SELECT f.file_path, COUNT(*) AS channel_count, f.multipart_count
FROM files f
JOIN channels c ON f.file_id = c.file_id
GROUP BY f.file_id, f.file_path, f.multipart_count
HAVING COUNT(*) > 20
ORDER BY channel_count DESC;
```

### Anomaly detection: uncompressed or oversized files

```sql
SELECT f.file_path, CAST(f.size_bytes AS DOUBLE) / (1024*1024) AS size_mb, p.compression
FROM files f
JOIN parts p ON f.file_id = p.file_id
WHERE p.compression = 'none' OR f.size_bytes > 500 * 1024 * 1024
ORDER BY f.size_bytes DESC;
```

## Vector Similarity Search

VAST DataBase supports vector distance functions via the ADBC driver:

| Function | Metric | Description |
|----------|--------|-------------|
| `array_distance(a, b)` | Euclidean (L2) | Lower = more similar |
| `array_cosine_distance(a, b)` | Cosine | Range [0, 2], lower = more similar |

### Find similar renders (via ADBC)

```sql
SELECT file_path, size_bytes, multipart_count
FROM "$DATABASE_BUCKET/exr_metadata"."files"
ORDER BY array_cosine_distance(metadata_embedding, $QUERY_VECTOR::FLOAT[384])
LIMIT 10;
```

### Python example

```python
from vast_db_persistence import compute_metadata_embedding

# Compute embedding for a reference file
ref = {
    "file": {"multipart_count": 1, "is_deep": False},
    "channels": [{"name": "R", "type": "float"}, {"name": "G", "type": "float"}],
    "parts": [{"compression": "piz", "is_tiled": True}],
}
query_vec = compute_metadata_embedding(ref)

# Query via ADBC driver
# See VAST documentation for ADBC connection setup
```
