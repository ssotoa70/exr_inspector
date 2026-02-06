# VAST DataBase Integration Guide

## Overview

The `vast_db_persistence.py` module provides production-ready persistence of EXR inspection results to VAST DataBase with deterministic vector embeddings, idempotent upserts, and comprehensive error handling.

## Architecture

### Components

1. **Vector Embeddings**
   - `compute_metadata_embedding()`: Deterministic 384-dim vector representing complete file metadata
   - `compute_channel_fingerprint()`: Deterministic 128-dim vector representing channel structure

2. **PyArrow Conversion**
   - `payload_to_files_row()`: Converts payload to file record with embedding
   - `payload_to_parts_rows()`: Converts payload to part records
   - `payload_to_channels_rows()`: Converts payload to channel records with fingerprint
   - `payload_to_attributes_rows()`: Converts payload to attribute records

3. **Session Management**
   - `_create_vastdb_session()`: Creates session from environment or event context
   - Stateless session handling for serverless execution
   - Graceful fallback if VAST DataBase not configured

4. **Idempotent Upsert**
   - `persist_to_vast_database()`: Main entry point with transaction management
   - `_persist_with_transaction()`: Orchestrates SELECT-then-INSERT pattern
   - `_select_existing_file()`: Checks existence by normalized path + header hash
   - `_update_audit_fields()`: Updates inspection timestamp and count
   - `_insert_new_file()`: Batch inserts across all tables

## Key Design Decisions

### Why SELECT-then-INSERT Instead of UPDATE

VAST DataBase has undocumented behavior for UPDATE operations using row IDs. To ensure predictable, auditable behavior:

1. **SELECT** by unique business key (file_path_normalized + header_hash)
2. **If found**: Skip insert (idempotent) or optionally UPDATE audit fields
3. **If not found**: INSERT complete record

Benefits:
- Idempotent: Multiple invocations produce same result
- Auditable: Clear INSERT vs UPDATE distinction in logs
- Predictable: No surprises with row ID semantics
- Testable: Easy to verify uniqueness constraints

### Deterministic Vector Embeddings

Embeddings are **deterministic**, not ML-based:
- Same payload always produces same vector
- Enables reproducible searches and clustering
- Avoids external ML dependencies in serverless
- Captures structural metadata (channels, compression, etc.)

**Metadata Embedding (384 dims)**:
- Features: channel count, part count, deep flag, tiling, multiview, compression type
- Hash: SHA256 of complete payload JSON normalized to float values
- Final: L2-normalized unit vector

**Channel Fingerprint (128 dims)**:
- Features: channel count, layer diversity, sampling patterns, type distribution
- Hash: MD5 of channel names concatenated
- Final: L2-normalized unit vector

These are suitable for:
- Vector similarity searches (find files with similar structure)
- Clustering metadata
- Pattern analysis across datasets
- Not suitable for: content-based similarity (use ML embeddings for that)

## Configuration

### Environment Variables

```bash
# VAST DataBase connection
VAST_DB_ENDPOINT="s3.region.vastdata.com"  # Required
VAST_DB_ACCESS_KEY="<AWS access key>"       # Required if using S3 auth
VAST_DB_SECRET_KEY="<AWS secret key>"       # Required if using S3 auth
VAST_DB_REGION="us-east-1"                  # Optional, default: us-east-1
VAST_DB_SCHEMA="exr_metadata"               # Optional, default: exr_metadata
```

### Event Context

Credentials can also be passed in DataEngine event:

```python
event = {
    "data": {
        "path": "/path/to/file.exr",
        "meta": True,
    },
    "vastdb_endpoint": "s3.region.vastdata.com",
    "vastdb_access_key": "...",
    "vastdb_secret_key": "...",
    "vastdb_region": "us-east-1",
}
```

## Database Schema

Expected tables in VAST DataBase:

### files
```
file_id (string, primary key)
file_path (string)
file_path_normalized (string, unique with header_hash)
header_hash (string, unique with file_path_normalized)
size_bytes (int64)
mtime (string, ISO8601)
multipart_count (int32)
is_deep (bool)
metadata_embedding (list<float32>[384])
inspection_timestamp (string, ISO8601)
inspection_count (int32)
last_inspected (string, ISO8601)
```

### parts
```
file_id (string, foreign key -> files)
file_path (string)
part_index (int32)
part_name (string)
view_name (string)
multi_view (bool)
data_window (string, JSON)
display_window (string, JSON)
pixel_aspect_ratio (float32)
line_order (string)
compression (string)
is_tiled (bool)
tile_width (int32)
tile_height (int32)
tile_depth (int32)
is_deep (bool)
```

### channels
```
file_id (string, foreign key -> files)
file_path (string)
part_index (int32)
channel_name (string)
channel_type (string)
x_sampling (int32)
y_sampling (int32)
channel_fingerprint (list<float32>[128])  # Only in first row per file
```

### attributes
```
file_id (string, foreign key -> files)
file_path (string)
part_index (int32)
attribute_name (string)
attribute_type (string)
attribute_value (string, JSON)
```

## Integration with main.py

### Basic Usage

```python
from vast_db_persistence import persist_to_vast_database

# In handler() function, after inspection:
payload = {
    "file": {"path": "/data/file.exr", "size_bytes": 1024000, ...},
    "channels": [...],
    "parts": [...],
    "attributes": {...},
}

persistence_result = persist_to_vast_database(payload, event)

# Add to response
result["persistence"] = persistence_result
```

### Return Value Structure

```python
{
    "status": "success" | "error" | "skipped",
    "file_id": "abc123...",  # UUID hex digest (16 chars)
    "inserted": True | False,  # True if new record, False if idempotent
    "message": "Human-readable status message",
    "error": None | "Error description"
}
```

### Response Examples

**Successful insertion**:
```json
{
    "status": "success",
    "file_id": "7f8a9b0c1d2e3f4a",
    "inserted": true,
    "message": "File persisted: 7f8a9b0c1d2e3f4a",
    "error": null
}
```

**Idempotent (already exists)**:
```json
{
    "status": "success",
    "file_id": "7f8a9b0c1d2e3f4a",
    "inserted": false,
    "message": "File already persisted: 7f8a9b0c1d2e3f4a",
    "error": null
}
```

**VAST not configured**:
```json
{
    "status": "skipped",
    "file_id": null,
    "inserted": false,
    "message": "VAST DataBase not configured",
    "error": null
}
```

**Error case**:
```json
{
    "status": "error",
    "file_id": null,
    "inserted": false,
    "message": "Vector embedding error",
    "error": "Failed to compute metadata embedding: invalid payload"
}
```

## Testing

### Local Testing (Without VAST)

```python
# Mock session
class MockSession:
    def begin(self):
        return self
    def commit(self):
        pass
    def rollback(self):
        pass
    def table(self, name):
        return MockTableClient()

class MockTableClient:
    def insert(self, table):
        print(f"Mock insert: {table.num_rows} rows")
    def select(self, query, params):
        return None  # Assume new file
    def update(self, query, params):
        pass

# Test with mock
payload = {...}
result = persist_to_vast_database(
    payload,
    event={},
    vastdb_session=MockSession()
)
assert result["status"] == "success"
```

### Testing Vector Embeddings

```python
from vast_db_persistence import compute_metadata_embedding

# Test determinism
payload = {"file": {...}, "channels": [...]}
vec1 = compute_metadata_embedding(payload)
vec2 = compute_metadata_embedding(payload)

assert len(vec1) == 384
assert all(abs(v1 - v2) < 1e-9 for v1, v2 in zip(vec1, vec2))

# Test unit norm
norm = sum(v * v for v in vec1) ** 0.5
assert abs(norm - 1.0) < 1e-6
```

### E2E Testing Against VAST Cluster

```bash
# Set credentials
export VAST_DB_ENDPOINT="s3.vastdata.com"
export VAST_DB_ACCESS_KEY="..."
export VAST_DB_SECRET_KEY="..."
export VAST_DB_SCHEMA="exr_metadata_test"

# Run inspection
python -c "
from functions.exr_inspector.main import handler
result = handler(None, {
    'data': {
        'path': '/path/to/test.exr',
        'meta': True
    }
})
print(result['persistence'])
"
```

## Performance Characteristics

### Embedding Computation
- **Metadata embedding**: ~1-2ms (SHA256 + normalization)
- **Channel fingerprint**: ~0.5-1ms (MD5 + normalization)
- **Total overhead**: <10ms for typical files

### PyArrow Conversion
- 1 files row: <1ms
- N parts rows: ~0.1ms per part
- M channels rows: ~0.1ms per channel
- K attributes rows: ~0.1ms per attribute

### Database Transaction
- SELECT by key: ~10-50ms (varies by cluster load)
- INSERT (all tables): ~50-200ms (depends on row count)
- COMMIT: ~10-50ms
- **Total**: 70-300ms per file

### Bottlenecks
1. Network latency to VAST endpoint
2. Transaction overhead (BEGIN/COMMIT)
3. Index updates for uniqueness constraints

### Optimization Tips
1. **Batch multiple files**: Queue mutations, flush periodically
2. **Reduce table columns**: Only persist required metadata
3. **Partition by mtime**: Helps with query performance
4. **Index on file_path_normalized**: For SELECT lookups

## Error Handling

### Connection Errors
If VAST endpoint is unreachable:
- Returns status="error" with connection error
- Transaction is rolled back
- Does not crash the handler

### Credential Errors
If credentials are invalid:
- Session creation fails
- Returns status="error"
- Handler continues to completion

### Schema Errors
If schema/tables don't exist:
- INSERT operation fails
- Transaction is rolled back
- Returns specific error message

### Embedding Errors
If vector computation fails (rare):
- Returns status="error" with computation details
- Original inspection result is still returned
- Allows downstream processing

### Recovery Strategy
1. Log all errors with context
2. Return clear error messages
3. Don't crash handler (let it complete)
4. Retry mechanism in DataEngine pipeline (if configured)

## Logging

The module uses Python logging with level DEBUG for verbose output:

```python
import logging
logging.basicConfig(level=logging.DEBUG)

# Example log output:
# INFO - VAST DataBase session created: s3.vastdata.com
# DEBUG - Computing embeddings for /data/file.exr
# DEBUG - Tables converted for abc123: files, parts, channels, attributes
# DEBUG - Transaction started for abc123
# INFO - File inserted: abc123
```

## Analytics Queries

### Find Files by Metadata Similarity

```sql
-- Find files similar to reference using vector distance
SELECT
    f.file_id,
    f.file_path,
    f.multipart_count,
    f.is_deep,
    -- Vector distance (approximation for L2 norm)
    SQRT(SUM((f.metadata_embedding - ref.metadata_embedding) ^ 2)) as distance
FROM files f, files ref
WHERE ref.file_id = 'reference_id'
    AND f.file_id != ref.file_id
ORDER BY distance ASC
LIMIT 10;
```

### Analyze Compression Usage

```sql
SELECT
    p.compression,
    COUNT(DISTINCT p.file_id) as file_count,
    AVG(f.size_bytes) as avg_size,
    COUNT(p.part_index) as total_parts
FROM parts p
JOIN files f ON p.file_id = f.file_id
GROUP BY p.compression
ORDER BY file_count DESC;
```

### Channel Configuration Analysis

```sql
SELECT
    c.channel_name,
    COUNT(DISTINCT c.file_id) as file_count,
    COUNT(DISTINCT c.channel_type) as type_variants,
    AVG(c.x_sampling) as avg_x_sampling,
    AVG(c.y_sampling) as avg_y_sampling
FROM channels c
GROUP BY c.channel_name
ORDER BY file_count DESC;
```

### Inspection Frequency

```sql
SELECT
    DATE_TRUNC('day', f.last_inspected) as inspection_date,
    COUNT(DISTINCT f.file_id) as files_inspected,
    SUM(f.inspection_count) as total_inspections,
    AVG(f.inspection_count) as avg_inspections_per_file
FROM files f
GROUP BY DATE_TRUNC('day', f.last_inspected)
ORDER BY inspection_date DESC;
```

## Dependencies

### Required
- `pyarrow>=10.0.0`: For PyArrow table creation and conversion
- `vastdb_sdk`: VAST DataBase Python SDK (must be installed in runtime)

### Optional
- `OpenImageIO`: For EXR inspection (already required by main module)

### Installation

```bash
pip install pyarrow>=10.0.0 vastdb-sdk
```

## Troubleshooting

### "VAST_DB_ENDPOINT not configured"
- Check environment variables: `printenv | grep VAST_DB`
- Or pass credentials in event context
- Or set status="skipped" is expected if not configured

### "pyarrow is required for payload conversion"
- Install pyarrow: `pip install pyarrow`
- Ensure it's in requirements.txt for Docker image

### "Session creation failed: Invalid credentials"
- Verify VAST_DB_ACCESS_KEY and VAST_DB_SECRET_KEY
- Check that endpoint is reachable
- Verify IAM credentials have S3 access

### "Transaction failed: Table not found"
- Verify VAST_DB_SCHEMA exists
- Create missing tables with proper schema
- Check table names match configuration

### "File already persisted (idempotent)"
- This is expected behavior on re-run
- Indicates previous successful persistence
- last_inspected will be updated
- inspection_count will be incremented

## Future Enhancements

1. **Async Persistence**: Decouple inspection from persistence for lower latency
2. **Batch Mode**: Queue multiple files, flush in batches
3. **Content Hashing**: Add pixel data hash for content-based deduplication
4. **ML Embeddings**: Integration with VAST Vector Search for deeper similarity
5. **Retention Policies**: Automatic cleanup of old inspection records
6. **Change Detection**: Compare vectors to detect structure changes

## Related Documentation

- `/docs/vast-integration.md`: VAST integration overview
- `/docs/deployment-checklist.md`: Deployment steps
- `main.py`: Integration entry point
- `requirements.txt`: Python dependencies for Docker build

## Support

For issues or questions:
1. Check logs: Look for DEBUG level output from vast_db_persistence module
2. Review error messages in result["persistence"]["error"]
3. Verify schema and table existence in VAST cluster
4. Consult VAST DataBase documentation for connection troubleshooting
