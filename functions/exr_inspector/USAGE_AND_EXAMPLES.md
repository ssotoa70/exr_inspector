# Usage and Examples Guide

## Quick Start

### Basic Integration

```python
from vast_db_persistence import persist_to_vast_database

# In your handler function after EXR inspection
payload = _inspect_exr(file_path)  # Returns JSON with metadata

result = persist_to_vast_database(payload, event)

if result["status"] == "success":
    print(f"File {result['file_id']} persisted (inserted={result['inserted']})")
elif result["status"] == "skipped":
    print("VAST DataBase not configured")
else:
    print(f"Error: {result['error']}")
```

### Return Handling

```python
# In main handler, include persistence result in response
def handler(ctx, event):
    payload = _inspect_exr(file_path)

    persistence_result = persist_to_vast_database(payload, event)

    return {
        "inspection": payload,
        "persistence": persistence_result,
        "timestamp": datetime.now().isoformat(),
    }
```

## Configuration Examples

### Environment Variables (Local Development)

```bash
# .env file or exported
export VAST_DB_ENDPOINT="s3.cluster.vastdata.com"
export VAST_DB_REGION="us-east-1"
export VAST_DB_ACCESS_KEY="AKIAIOSFODNN7EXAMPLE"
export VAST_DB_SECRET_KEY="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
export VAST_DB_SCHEMA="exr_metadata"
```

### DataEngine Event Context

```python
# If VAST credentials are provided via DataEngine
event = {
    "data": {
        "path": "/renders/output/shot_001.exr",
        "meta": True,
        "stats": False,
    },
    # VAST credentials (alternative to env vars)
    "vastdb_endpoint": "s3.cluster.vastdata.com",
    "vastdb_region": "us-east-1",
    "vastdb_access_key": "AKIA...",
    "vastdb_secret_key": "wJal...",
}

result = handler(None, event)
```

### Custom Schema Name

```bash
# Use non-default schema name
export VAST_DB_SCHEMA="custom_exr_schema"
```

## Vector Embedding Examples

### Direct Embedding Computation

```python
from vast_db_persistence import (
    compute_metadata_embedding,
    compute_channel_fingerprint,
)

# Compute metadata embedding (384 dims)
payload = {
    "file": {
        "multipart_count": 2,
        "is_deep": False,
    },
    "channels": [
        {"name": "R", "type": "float"},
        {"name": "G", "type": "float"},
        {"name": "B", "type": "float"},
    ],
    "parts": [
        {"compression": "piz", "is_tiled": True},
        {"compression": "zip", "is_tiled": False},
    ],
}

metadata_vec = compute_metadata_embedding(payload)
print(f"Metadata embedding: {len(metadata_vec)} dims, norm={sum(v*v for v in metadata_vec)**0.5:.6f}")

# Compute channel fingerprint (128 dims)
channel_fp = compute_channel_fingerprint(payload["channels"])
print(f"Channel fingerprint: {len(channel_fp)} dims, norm={sum(v*v for v in channel_fp)**0.5:.6f}")
```

### Deterministic Verification

```python
# Verify embeddings are deterministic
payload = {
    "file": {"multipart_count": 1},
    "channels": [{"name": "R", "type": "float"}],
    "parts": [{"compression": "zip"}],
}

vec1 = compute_metadata_embedding(payload)
vec2 = compute_metadata_embedding(payload)

assert vec1 == vec2, "Embeddings should be identical"
print("Determinism verified: same payload = same vector")
```

### Custom Dimensions

```python
# Use different embedding dimensions
vec_64 = compute_metadata_embedding(payload, embedding_dim=64)
vec_256 = compute_metadata_embedding(payload, embedding_dim=256)
vec_512 = compute_metadata_embedding(payload, embedding_dim=512)

print(f"64-dim: {len(vec_64)}")
print(f"256-dim: {len(vec_256)}")
print(f"512-dim: {len(vec_512)}")
```

## Testing Examples

### Unit Test Template

```python
import unittest
from vast_db_persistence import compute_metadata_embedding

class TestEmbeddings(unittest.TestCase):
    def test_embedding_output_shape(self):
        payload = {
            "file": {"multipart_count": 1},
            "channels": [],
            "parts": [],
        }

        vec = compute_metadata_embedding(payload)
        self.assertEqual(len(vec), 384)

    def test_embedding_is_normalized(self):
        payload = {...}
        vec = compute_metadata_embedding(payload)
        norm = sum(v*v for v in vec) ** 0.5
        self.assertAlmostEqual(norm, 1.0, places=5)
```

### Mock Session Testing

```python
from unittest.mock import MagicMock
from vast_db_persistence import persist_to_vast_database

def test_persistence_with_mock():
    # Create mock session
    mock_session = MagicMock()
    mock_txn = MagicMock()
    mock_table = MagicMock()

    mock_session.begin.return_value = mock_txn
    mock_session.table.return_value = mock_table
    mock_table.select.return_value = None  # No existing file

    # Test persistence
    payload = {
        "file": {"path": "/data/test.exr", ...},
        "channels": [...],
        "parts": [...],
        "attributes": {"parts": [[]]},
    }

    result = persist_to_vast_database(payload, {}, mock_session)

    assert result["status"] == "success"
    assert result["inserted"] == True
    mock_txn.commit.assert_called_once()
    print("Mock test passed!")

test_persistence_with_mock()
```

### Idempotency Testing

```python
# Simulate re-running on same file
payload = {"file": {"path": "/data/file.exr"}, ...}

# First run: new file
result1 = persist_to_vast_database(payload, {}, mock_session)
assert result1["inserted"] == True
assert result1["status"] == "success"
file_id_1 = result1["file_id"]

# Second run: same file (idempotent)
mock_table.select.return_value = [{"file_id": file_id_1}]  # File exists
result2 = persist_to_vast_database(payload, {}, mock_session)

assert result2["inserted"] == False
assert result2["status"] == "success"
assert result2["file_id"] == file_id_1
print("Idempotency verified!")
```

## Integration Examples

### DataEngine Pipeline Integration

```python
# In DataEngine pipeline handler
from vast_db_persistence import persist_to_vast_database

def handler(ctx, event):
    """DataEngine function handler."""
    file_path = event.get("data", {}).get("path")

    if not file_path:
        return {"status": "error", "message": "Missing file path"}

    # Inspect file
    inspection_result = inspect_exr_file(file_path)

    # Persist to VAST DataBase
    persistence_result = persist_to_vast_database(
        inspection_result,
        event,
    )

    # Return combined result
    return {
        "file": file_path,
        "inspection": inspection_result,
        "persistence": persistence_result,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
```

### Batch Processing

```python
# Process multiple files in batch
from vast_db_persistence import persist_to_vast_database

def batch_inspect_and_persist(file_list, event, session=None):
    """Process multiple EXR files."""
    results = {
        "total": len(file_list),
        "successful": 0,
        "failed": 0,
        "skipped": 0,
        "files": [],
    }

    for file_path in file_list:
        try:
            # Inspect file
            inspection = inspect_exr_file(file_path)

            # Persist to database
            event["data"]["path"] = file_path
            persist_result = persist_to_vast_database(
                inspection,
                event,
                vastdb_session=session,
            )

            results["files"].append({
                "path": file_path,
                "file_id": persist_result.get("file_id"),
                "status": persist_result["status"],
            })

            if persist_result["status"] == "success":
                results["successful"] += 1
            elif persist_result["status"] == "skipped":
                results["skipped"] += 1
            else:
                results["failed"] += 1

        except Exception as e:
            results["failed"] += 1
            results["files"].append({
                "path": file_path,
                "error": str(e),
            })

    return results

# Usage
files = [
    "/renders/shot_001.exr",
    "/renders/shot_002.exr",
    "/renders/shot_003.exr",
]

results = batch_inspect_and_persist(files, event)
print(f"Processed {results['total']} files: "
      f"{results['successful']} success, "
      f"{results['failed']} failed")
```

### Error Recovery

```python
# Graceful error handling with logging
import logging

logger = logging.getLogger(__name__)

def safe_persist(payload, event, max_retries=3):
    """Persist with retry logic."""
    for attempt in range(max_retries):
        try:
            result = persist_to_vast_database(payload, event)

            if result["status"] == "success":
                logger.info(f"File {result['file_id']} persisted")
                return result
            elif result["status"] == "skipped":
                logger.debug("VAST DataBase not configured")
                return result
            else:
                logger.warning(f"Persistence failed: {result['error']}")
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)  # Exponential backoff
                    continue
                else:
                    raise Exception(result['error'])

        except Exception as e:
            logger.exception(f"Attempt {attempt + 1} failed: {e}")
            if attempt == max_retries - 1:
                return {
                    "status": "error",
                    "error": str(e),
                    "file_id": None,
                }

# Usage
result = safe_persist(payload, event)
```

## Database Query Examples

### Vector Similarity Search

```sql
-- Find files similar to reference (using approximate L2 distance)
WITH reference AS (
    SELECT metadata_embedding
    FROM exr_metadata.files
    WHERE file_id = 'reference_file_id'
)
SELECT
    f.file_id,
    f.file_path,
    f.multipart_count,
    -- L2 distance approximation
    SQRT(SUM(POW(f.metadata_embedding[i] - r.metadata_embedding[i], 2)))
        OVER () as distance
FROM exr_metadata.files f
CROSS JOIN reference r
WHERE f.file_id != 'reference_file_id'
ORDER BY distance ASC
LIMIT 10;
```

### Complex Channel Analysis

```sql
-- Find all files with specific channel configuration
SELECT
    f.file_id,
    f.file_path,
    f.size_bytes,
    STRING_AGG(DISTINCT c.channel_name, ', ') as channels,
    COUNT(DISTINCT c.channel_type) as unique_types
FROM exr_metadata.files f
JOIN exr_metadata.channels c ON f.file_id = c.file_id
WHERE f.file_path LIKE '%.exr'
GROUP BY f.file_id, f.file_path, f.size_bytes
HAVING STRING_AGG(DISTINCT c.channel_name, ', ')
        LIKE '%R%G%B%A%'  -- Must have RGBA
ORDER BY f.size_bytes DESC;
```

### Deep File Analysis

```sql
-- Analyze deep (volumetric) EXR files
SELECT
    f.file_id,
    f.file_path,
    COUNT(DISTINCT p.part_index) as part_count,
    SUM(CASE WHEN p.is_tiled THEN 1 ELSE 0 END) as tiled_parts,
    STRING_AGG(DISTINCT p.compression, ', ') as compressions,
    AVG(f.inspection_count) as avg_inspections
FROM exr_metadata.files f
JOIN exr_metadata.parts p ON f.file_id = p.file_id
WHERE f.is_deep = true
GROUP BY f.file_id, f.file_path
ORDER BY part_count DESC;
```

### Inspection Trends

```sql
-- Weekly inspection trends
SELECT
    DATE_TRUNC('week', f.inspection_timestamp) as week,
    COUNT(DISTINCT f.file_id) as new_files,
    SUM(f.inspection_count) as total_inspections,
    ROUND(AVG(f.size_bytes) / 1024 / 1024, 2) as avg_size_mb,
    ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP
        (ORDER BY f.size_bytes) / 1024 / 1024, 2) as median_size_mb
FROM exr_metadata.files f
GROUP BY DATE_TRUNC('week', f.inspection_timestamp)
ORDER BY week DESC
LIMIT 52;
```

## Performance Optimization Examples

### Bulk Insert Optimization

```python
# Queue and batch inserts for higher throughput
from vast_db_persistence import persist_to_vast_database

class PersistenceQueue:
    def __init__(self, batch_size=10, session=None):
        self.batch_size = batch_size
        self.queue = []
        self.session = session

    def add(self, payload, event):
        self.queue.append((payload, event))
        if len(self.queue) >= self.batch_size:
            self.flush()

    def flush(self):
        results = []
        for payload, event in self.queue:
            result = persist_to_vast_database(
                payload,
                event,
                vastdb_session=self.session,
            )
            results.append(result)
        self.queue.clear()
        return results

# Usage
queue = PersistenceQueue(batch_size=50)
for file_path in large_file_list:
    payload = inspect_exr_file(file_path)
    queue.add(payload, event)
queue.flush()
```

### Connection Reuse

```python
# Reuse session for multiple operations
from vastdb_sdk import Session

def process_many_files(file_list, event):
    # Create single session for all operations
    session = Session(
        endpoint=os.environ.get("VAST_DB_ENDPOINT"),
        access_key=os.environ.get("VAST_DB_ACCESS_KEY"),
        secret_key=os.environ.get("VAST_DB_SECRET_KEY"),
    )

    try:
        results = []
        for file_path in file_list:
            payload = inspect_exr_file(file_path)
            result = persist_to_vast_database(
                payload,
                event,
                vastdb_session=session,  # Reuse session
            )
            results.append(result)
        return results
    finally:
        # Clean up session
        session.close()
```

## Monitoring Examples

### Performance Tracking

```python
import time
import logging

logger = logging.getLogger(__name__)

def persist_with_timing(payload, event):
    """Track persistence performance."""
    start = time.time()

    # Compute embeddings
    emb_start = time.time()
    from vast_db_persistence import compute_metadata_embedding
    metadata_embedding = compute_metadata_embedding(payload)
    emb_time = time.time() - emb_start

    # Persist
    persist_start = time.time()
    result = persist_to_vast_database(payload, event)
    persist_time = time.time() - persist_start

    total_time = time.time() - start

    logger.info(
        f"Persistence timing: embedding={emb_time*1000:.1f}ms, "
        f"persist={persist_time*1000:.1f}ms, "
        f"total={total_time*1000:.1f}ms, "
        f"status={result['status']}"
    )

    return result
```

### Health Checks

```python
def check_vast_connectivity():
    """Verify VAST DataBase is accessible."""
    try:
        from vast_db_persistence import _create_vastdb_session
        session = _create_vastdb_session({})

        if session is None:
            return {"status": "not_configured"}

        # Try a simple query
        result = session.table("exr_metadata.files").select(
            "SELECT COUNT(*) as count FROM files LIMIT 1"
        )

        return {"status": "healthy", "files_count": result[0]["count"]}

    except Exception as e:
        return {"status": "error", "error": str(e)}

# Usage
health = check_vast_connectivity()
print(f"VAST DataBase: {health['status']}")
```

## Best Practices Summary

1. **Always check return status** - `result["status"]` can be "success", "error", or "skipped"
2. **Use environment variables** for credentials - never hardcode secrets
3. **Verify embeddings are normalized** - L2 norm should be ~1.0
4. **Test with mock session first** - before running against cluster
5. **Batch operations when possible** - for better performance
6. **Log all errors clearly** - includes `result["error"]` message
7. **Handle gracefully** - persistence failure should not crash inspection
8. **Monitor performance** - track embedding and persistence latencies
9. **Use deterministic embeddings** - same file always produces same vector
10. **Verify idempotency** - re-running should produce same results

## Troubleshooting Checklist

- [ ] VAST_DB_ENDPOINT is set and reachable
- [ ] AWS credentials are valid and have S3 access
- [ ] Database schema and tables exist
- [ ] pyarrow and vastdb-sdk are installed
- [ ] Embeddings are computed and normalized
- [ ] Mock testing works before cluster testing
- [ ] Error messages are clear and actionable
- [ ] Logs show successful connections
- [ ] Verification queries return data
- [ ] Performance is acceptable (< 500ms per file)
