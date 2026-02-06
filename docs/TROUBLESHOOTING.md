# Troubleshooting Guide

## Overview

This document provides solutions for common issues encountered when using exr-inspector with VAST Database. Use this guide to diagnose and resolve problems.

---

## Connection Issues

### Error: "VAST_DB_ENDPOINT not configured"

**Symptom**: Persistence is skipped, no data inserted.

**Root Cause**: VAST Database endpoint not set or empty.

**Solutions**:

1. **Check environment variables**:
   ```bash
   echo $VAST_DB_ENDPOINT
   echo $VAST_DB_ACCESS_KEY
   ```
   If empty, set them:
   ```bash
   export VAST_DB_ENDPOINT="https://vast-db-us-east-1.example.com"
   export VAST_DB_ACCESS_KEY="your-access-key"
   export VAST_DB_SECRET_KEY="your-secret-key"
   ```

2. **Check event context** (DataEngine):
   ```python
   # In handler, verify event contains VAST credentials
   print(f"Endpoint from event: {event.get('vastdb_endpoint')}")
   ```

3. **Check priority order**:
   - Event context has highest priority
   - Falls back to environment variables
   - Default region is "us-east-1"

**Verification**:
```python
from vast_db_persistence import _create_vastdb_session

session = _create_vastdb_session({"vastdb_endpoint": "https://..."})
if session:
    print("Connection successful!")
else:
    print("Failed to create session")
```

---

### Error: "Failed to create VAST DataBase session"

**Symptom**: Connection fails with detailed error message.

**Root Cause**: Invalid credentials or unreachable endpoint.

**Solutions**:

1. **Verify endpoint is accessible**:
   ```bash
   curl -I https://your-vast-endpoint.example.com
   # Should return 200 or 401 (not 404 or timeout)
   ```

2. **Verify credentials are valid**:
   ```bash
   # Use VAST CLI to test credentials
   vast auth verify \
       --endpoint https://your-endpoint.example.com \
       --access-key your-key \
       --secret-key your-secret
   ```

3. **Check endpoint format**:
   ```python
   # Must be full URL with protocol
   endpoint = "https://vast.example.com"  # Correct
   endpoint = "vast.example.com"          # Wrong
   endpoint = "http://vast.example.com"   # Wrong (use HTTPS)
   ```

4. **Check credential character encoding**:
   ```python
   # Some credentials contain special characters
   # Ensure proper URL encoding
   import urllib.parse
   secret = urllib.parse.quote(raw_secret, safe='')
   ```

5. **Check network connectivity** (serverless):
   ```python
   # If running in DataEngine, verify VAST is accessible
   import socket
   hostname = "vast.example.com"
   try:
       socket.gethostbyname(hostname)
       print("DNS resolution OK")
   except:
       print("Cannot resolve hostname - check VPC/network settings")
   ```

**Debug Logging**:
```python
import logging
logging.basicConfig(level=logging.DEBUG)

# Enable VAST SDK debugging (if available)
logging.getLogger('vastdb_sdk').setLevel(logging.DEBUG)

# Now run persistence
result = persist_to_vast_database(payload, event)
```

---

### Error: "Connection timeout"

**Symptom**: Operation hangs for 30+ seconds, then fails with timeout.

**Root Cause**: VAST endpoint unreachable or overloaded.

**Solutions**:

1. **Check endpoint status**:
   ```bash
   # Check if VAST service is running
   curl -w "@curl-format.txt" -o /dev/null -s https://vast.example.com/health
   ```

2. **Check network path**:
   ```bash
   # Trace network path to endpoint
   traceroute vast.example.com

   # Test connectivity from serverless environment
   python -c "
   import socket, time
   s = socket.socket()
   start = time.time()
   try:
       s.connect(('vast.example.com', 443))
       print(f'Connected in {time.time()-start:.2f}s')
   except TimeoutError:
       print('Timeout - endpoint unreachable')
   finally:
       s.close()
   "
   ```

3. **Increase timeout** (if supported by SDK):
   ```python
   session = Session(
       endpoint="https://vast.example.com",
       access_key="...",
       secret_key="...",
       timeout=30,  # seconds
       connect_timeout=10,
   )
   ```

4. **Check for firewall rules**:
   - Ensure egress on port 443 allowed
   - Check security groups (AWS)
   - Verify VPC routing

---

## Vector Embedding Issues

### Error: "Failed to compute metadata embedding"

**Symptom**: Embedding computation fails, file not persisted.

**Root Cause**: Invalid or malformed inspection payload.

**Solutions**:

1. **Validate payload structure**:
   ```python
   from vast_db_persistence import compute_metadata_embedding

   try:
       embedding = compute_metadata_embedding(payload)
       print(f"Success: {len(embedding)}D vector")
   except Exception as e:
       print(f"Error: {e}")
       print(f"Payload keys: {list(payload.keys())}")
       print(f"File info: {payload.get('file', {})}")
   ```

2. **Check required keys**:
   ```python
   # Payload must have these top-level keys:
   required_keys = ["file", "channels", "parts"]
   for key in required_keys:
       if key not in payload:
           print(f"Missing required key: {key}")

   # file must have path
   if "path" not in payload.get("file", {}):
       print("Missing file.path")
   ```

3. **Check for invalid types**:
   ```python
   payload = {
       "file": {...},           # Must be dict
       "channels": [...],       # Must be list
       "parts": [...],          # Must be list
       "attributes": {...},     # Must be dict
   }
   ```

4. **Serialize payload for debugging**:
   ```python
   import json
   print(json.dumps(payload, indent=2, default=str))
   # Look for non-serializable objects (None is OK)
   ```

5. **Test with minimal payload**:
   ```python
   minimal = {
       "file": {"path": "/test.exr"},
       "channels": [],
       "parts": []
   }
   embedding = compute_metadata_embedding(minimal)
   print(f"Minimal test passed: {len(embedding)}D")
   ```

---

### Error: "Vector size mismatch"

**Symptom**: Insertion fails with "expected 384 dimensions, got X".

**Root Cause**: Embedding dimension doesn't match schema.

**Solutions**:

1. **Verify default dimensions**:
   ```python
   from vast_db_persistence import (
       DEFAULT_METADATA_EMBEDDING_DIM,
       DEFAULT_CHANNEL_FINGERPRINT_DIM,
   )
   print(f"Metadata embedding: {DEFAULT_METADATA_EMBEDDING_DIM}D")
   print(f"Channel fingerprint: {DEFAULT_CHANNEL_FINGERPRINT_DIM}D")
   ```

2. **Verify computation output**:
   ```python
   embedding = compute_metadata_embedding(payload)
   print(f"Embedding length: {len(embedding)}")
   print(f"All floats: {all(isinstance(v, float) for v in embedding)}")

   # Check for NaN or Inf
   import math
   for i, v in enumerate(embedding):
       if math.isnan(v) or math.isinf(v):
           print(f"  Position {i}: {v}")
   ```

3. **Check schema definition**:
   ```python
   from vast_schemas import FILES_SCHEMA

   metadata_field = FILES_SCHEMA.field("metadata_embedding")
   print(f"Schema expects: {metadata_field}")
   # Should be list of float32, dimension metadata shows 384 or 512
   ```

4. **Explicit dimension specification**:
   ```python
   # If you need different dimension:
   embedding_384 = compute_metadata_embedding(payload, embedding_dim=384)
   embedding_512 = compute_metadata_embedding(payload, embedding_dim=512)

   # But must match schema!
   ```

---

### Error: "Vector is not normalized"

**Symptom**: Vector computation produces magnitude != 1.0, queries behave oddly.

**Root Cause**: Normalization failed or edge case (all zeros).

**Solutions**:

1. **Check normalization**:
   ```python
   embedding = compute_metadata_embedding(payload)

   # Compute L2 norm
   import math
   norm = math.sqrt(sum(v * v for v in embedding))
   print(f"L2 norm: {norm:.9f}")
   # Should be ~1.0 (within 1e-6)

   if norm < 0.99 or norm > 1.01:
       print(f"WARNING: Vector not properly normalized!")
   ```

2. **Check for degenerate case**:
   ```python
   # All-zeros payload produces uniform vector
   payload_empty = {
       "file": {"path": "/test.exr"},
       "channels": [],
       "parts": []
   }
   embedding = compute_metadata_embedding(payload_empty)
   # Should be [1/sqrt(384), 1/sqrt(384), ...]
   expected_val = 1.0 / math.sqrt(384)
   all_equal = all(abs(v - expected_val) < 1e-6 for v in embedding)
   print(f"Uniform degenerate case: {all_equal}")
   ```

3. **Test with varied payload**:
   ```python
   # Try payload with more structure
   test_payload = {
       "file": {
           "path": "/renders/test.exr",
           "multipart_count": 2,
           "is_deep": False,
           "size_bytes": 104857600,
       },
       "channels": [
           {"name": "R", "type": "float", "x_sampling": 1, "y_sampling": 1},
           {"name": "G", "type": "float", "x_sampling": 1, "y_sampling": 1},
       ],
       "parts": [{"compression": "zip"}],
   }
   embedding = compute_metadata_embedding(test_payload)
   norm = math.sqrt(sum(v * v for v in embedding))
   print(f"Norm: {norm:.9f}")
   ```

---

## Transaction Failures

### Error: "Transaction failed"

**Symptom**: Insert fails mid-transaction, file not persisted.

**Root Cause**: Database error during INSERT or SELECT.

**Solutions**:

1. **Check for transaction rollback**:
   ```python
   # Look for "Transaction rolled back" in logs
   # This means one of the INSERT statements failed
   ```

2. **Verify tables exist**:
   ```python
   from vastdb_sdk import Session

   session = Session(...)

   # Check each table
   for table_name in ["files", "parts", "channels", "attributes"]:
       try:
           t = session.table(f"exr_metadata.{table_name}")
           print(f"✓ {table_name} exists")
       except Exception as e:
           print(f"✗ {table_name} missing: {e}")
   ```

3. **Check schema exists**:
   ```python
   # Ensure schema is created first
   try:
       session.execute("SELECT 1 FROM exr_metadata.files LIMIT 1")
       print("Schema exists")
   except:
       print("Schema not found - run schema initialization")
       # Create schema and tables from vast_schemas.py
   ```

4. **Check for constraint violations**:
   ```python
   # Unique constraint on file_path_normalized + header_hash
   # If exact same file inserted twice, second fails

   # Check if file already exists:
   query = """
   SELECT file_id FROM files
   WHERE file_path_normalized = ?
   AND header_hash = ?
   """
   results = files_table.select(query, [normalized_path, header_hash])
   if results:
       print(f"File already exists: {results[0]['file_id']}")
   ```

5. **Check individual table inserts**:
   ```python
   # Test each table separately
   try:
       files_table.insert(files_table_data)
       print("✓ Files insert OK")
   except Exception as e:
       print(f"✗ Files insert failed: {e}")

   try:
       parts_table.insert(parts_table_data)
       print("✓ Parts insert OK")
   except Exception as e:
       print(f"✗ Parts insert failed: {e}")
   ```

---

### Error: "Rollback failed"

**Symptom**: Transaction error AND rollback error both logged.

**Root Cause**: Database connection lost or VAST session invalid.

**Solutions**:

1. **Reconnect and retry**:
   ```python
   # Create new session if rollback fails
   try:
       txn.rollback()
   except:
       # Session may be broken, create new one
       session = Session(...)  # Fresh connection
       # Try to reclaim any partial state
   ```

2. **Check VAST Database health**:
   ```bash
   # From VAST CLI
   vast db health

   # Check logs
   vast logs --component database --tail 100
   ```

3. **Implement connection pooling**:
   ```python
   # For repeated calls, reuse session
   _session_cache = {}

   def get_session(key: str, endpoint: str) -> Session:
       if key not in _session_cache:
           _session_cache[key] = Session(endpoint=endpoint, ...)
       return _session_cache[key]
   ```

---

## Data Type Conversion Errors

### Error: "Cannot convert int32 to float32"

**Symptom**: PyArrow table conversion fails.

**Root Cause**: Type mismatch in payload data.

**Solutions**:

1. **Check channel types**:
   ```python
   # channel_type must be string: "FLOAT", "HALF", "UINT", etc.
   for channel in payload.get("channels", []):
       ch_type = channel.get("type")
       if not isinstance(ch_type, str):
           print(f"ERROR: channel type must be string, got {type(ch_type)}")
   ```

2. **Check numeric fields**:
   ```python
   # These must be integers
   for part in payload.get("parts", []):
       for field in ["part_index", "tile_width", "tile_height"]:
           if field in part:
               val = part[field]
               if not isinstance(val, (int, type(None))):
                   print(f"ERROR: {field} must be int, got {type(val)}")
   ```

3. **Check file size field**:
   ```python
   file_info = payload.get("file", {})
   size_bytes = file_info.get("size_bytes")
   if not isinstance(size_bytes, int):
       print(f"ERROR: size_bytes must be int, got {type(size_bytes)}")
   ```

4. **Convert types explicitly**:
   ```python
   # If data comes from JSON or other source with type issues:
   def clean_payload(payload):
       # Fix integers
       payload["file"]["size_bytes"] = int(payload["file"].get("size_bytes", 0))
       payload["file"]["multipart_count"] = int(payload["file"].get("multipart_count", 1))

       # Fix booleans
       payload["file"]["is_deep"] = bool(payload["file"].get("is_deep", False))

       return payload
   ```

---

## Performance Issues

### Problem: "Vector queries are slow (>5 seconds)"

**Symptom**: `DISTANCE()` queries on large tables timeout or return slowly.

**Root Cause**: Missing indexes, unoptimized query, or large result set.

**Solutions**:

1. **Create indexes**:
   ```sql
   -- Index the embedding vector for faster distance searches
   CREATE INDEX idx_files_metadata_embedding
   ON files USING gist (metadata_embedding);

   CREATE INDEX idx_channels_fingerprint
   ON channels USING gist (channel_fingerprint);

   -- Also index common filter columns
   CREATE INDEX idx_files_path_normalized
   ON files (file_path_normalized);

   CREATE INDEX idx_files_is_deep
   ON files (is_deep);
   ```

2. **Limit result set**:
   ```sql
   -- Always use LIMIT for distance queries
   SELECT file_id, file_path,
          DISTANCE(metadata_embedding, ?, 'cosine') as distance
   FROM files
   WHERE DISTANCE(metadata_embedding, ?, 'cosine') < 0.5
   ORDER BY distance ASC
   LIMIT 100  -- Add LIMIT!
   ```

3. **Filter before distance calculation**:
   ```sql
   -- Narrow down search space first
   SELECT file_id, file_path,
          DISTANCE(metadata_embedding, ?, 'cosine') as distance
   FROM files
   WHERE is_deep = false          -- Filter first
   AND size_bytes < 500*1024*1024 -- Then calculate distance
   AND DISTANCE(metadata_embedding, ?, 'cosine') < 0.3
   ORDER BY distance ASC
   LIMIT 100
   ```

4. **Use EXPLAIN to analyze query**:
   ```sql
   EXPLAIN SELECT file_id,
           DISTANCE(metadata_embedding, ?, 'cosine') as dist
   FROM files
   LIMIT 100;

   -- Look for sequential scans (slow)
   -- vs index scans (fast)
   ```

5. **Partition table by date**:
   ```sql
   -- For very large tables (>10M rows), partition
   CREATE TABLE files_2025_02 PARTITION OF files
   FOR VALUES FROM ('2025-02-01') TO ('2025-03-01');
   ```

6. **Pre-compute similarity scores**:
   ```python
   # Instead of computing on-demand, pre-compute for common queries
   # Store in materialized view

   CREATE MATERIALIZED VIEW similar_files AS
   SELECT f1.file_id as ref_id,
          f2.file_id as similar_id,
          DISTANCE(f1.metadata_embedding, f2.metadata_embedding, 'cosine') as distance
   FROM files f1
   CROSS JOIN files f2
   WHERE f1.file_id < f2.file_id
   AND DISTANCE(f1.metadata_embedding, f2.metadata_embedding, 'cosine') < 0.3;

   -- Refresh periodically
   REFRESH MATERIALIZED VIEW similar_files;
   ```

---

### Problem: "Embedding computation is slow"

**Symptom**: Single file inspection takes >100ms.

**Root Cause**: Payload is very large or serialization is slow.

**Solutions**:

1. **Profile computation**:
   ```python
   import time

   start = time.time()
   embedding = compute_metadata_embedding(payload)
   elapsed = time.time() - start

   print(f"Embedding computed in {elapsed*1000:.2f}ms")
   ```

2. **Check payload size**:
   ```python
   import json
   import sys

   payload_json = json.dumps(payload, default=str)
   size_bytes = len(payload_json.encode())
   print(f"Payload size: {size_bytes / 1024:.1f} KB")

   if size_bytes > 1_000_000:
       print("WARNING: Payload >1MB - consider filtering")
   ```

3. **Optimize feature extraction**:
   ```python
   # If many channels/parts, extract features is fast
   # Bottleneck is usually JSON serialization for hashing
   # Consider sampling for very large payloads
   ```

4. **Cache embeddings**:
   ```python
   _embedding_cache = {}

   def cached_embedding(payload):
       # Use file path as cache key
       key = payload["file"]["path"]
       if key not in _embedding_cache:
           _embedding_cache[key] = compute_metadata_embedding(payload)
       return _embedding_cache[key]
   ```

---

## Validation and Policy Issues

### Error: "Validation policy not found"

**Symptom**: enable_validate=True but no results returned.

**Root Cause**: Policy file path incorrect or validation not implemented.

**Solutions**:

1. **Check policy file**:
   ```python
   policy_path = event["data"].get("policy_path")
   if policy_path:
       import os
       if not os.path.exists(policy_path):
           print(f"Policy file not found: {policy_path}")
   ```

2. **Note**: Validation is currently stubbed in v1.0.0:
   ```python
   # In main.py, validation_placeholder() returns:
   {
       "status": "skipped",
       "reason": "validation not implemented"
   }
   ```

3. **To enable validation**:
   - Implement actual policy checking in `main.py`
   - Insert results into `validation_results` table
   - See VAST_ANALYTICS_QUERIES.md for validation schema

---

## Debugging Tips

### Enable Verbose Logging

```python
import logging
import sys

# Configure root logger
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stdout
)

# Enable specific module loggers
logging.getLogger('vast_db_persistence').setLevel(logging.DEBUG)
logging.getLogger('vastdb_sdk').setLevel(logging.DEBUG)

# Now run handler
result = handler(ctx, event)
```

### Print Full Payloads

```python
import json

print("=== FULL PAYLOAD ===")
print(json.dumps(payload, indent=2, default=str))

print("\n=== METADATA ONLY ===")
print(json.dumps(payload.get("file", {}), indent=2))

print("\n=== CHANNELS ===")
for i, ch in enumerate(payload.get("channels", [])):
    print(f"  {i}: {ch['name']} ({ch['type']})")
```

### Validate at Each Step

```python
def validate_pipeline(payload, event):
    """Validate each step of the pipeline."""

    # Step 1: Payload structure
    assert "file" in payload, "Missing 'file' key"
    assert "path" in payload["file"], "Missing 'file.path'"
    print("✓ Payload structure OK")

    # Step 2: Embedding computation
    try:
        emb = compute_metadata_embedding(payload)
        assert len(emb) == 384, f"Wrong embedding size: {len(emb)}"
        norm = sum(v * v for v in emb) ** 0.5
        assert 0.99 < norm < 1.01, f"Not normalized: {norm:.6f}"
        print("✓ Embedding OK")
    except Exception as e:
        print(f"✗ Embedding failed: {e}")
        return False

    # Step 3: PyArrow conversion
    try:
        files_table = payload_to_files_row(payload, emb)
        assert files_table.num_rows == 1, "Wrong row count"
        print("✓ PyArrow conversion OK")
    except Exception as e:
        print(f"✗ PyArrow conversion failed: {e}")
        return False

    # Step 4: VAST session
    try:
        session = _create_vastdb_session(event)
        assert session is not None, "No session created"
        print("✓ VAST session OK")
    except Exception as e:
        print(f"✗ VAST session failed: {e}")
        return False

    print("\n✓ All validations passed!")
    return True
```

### Compare with Test Cases

```bash
# Run unit tests to verify components work
python -m pytest test_vast_db_persistence.py -v

# Run specific test
python -m pytest test_vast_db_persistence.py::TestVectorEmbeddings::test_metadata_embedding_determinism -v

# Useful tests:
# - test_metadata_embedding_unit_norm (checks L2 = 1.0)
# - test_payload_to_files_row_basic (checks conversion)
# - test_persist_new_file_success (checks full pipeline)
```

---

## Contact and Support

For issues not covered here:

1. **Check logs**:
   ```bash
   # DataEngine
   vast function logs exr-inspector --tail 50

   # VAST Database
   vast db logs --tail 100

   # Local (Python)
   python main.py 2>&1 | tee debug.log
   ```

2. **Enable debug mode**:
   ```python
   import os
   os.environ['DEBUG'] = '1'
   os.environ['LOG_LEVEL'] = 'DEBUG'
   ```

3. **File an issue** with:
   - Error message (full traceback)
   - Payload size and structure
   - VAST endpoint version
   - Python/PyArrow versions
   - Recent config changes

---

## Rollback Procedures

### Overview

Rollback procedures allow you to revert to a previous version of exr-inspector if issues arise during or after deployment.

### Pre-Rollback Checklist

Before initiating a rollback, verify:

1. **Issue severity**: Is this a critical issue (data loss, security) or minor issue?
2. **Impact scope**: How many files/operations are affected?
3. **Backup status**: Is a backup of the database available?
4. **Rollback window**: How much downtime is acceptable?

---

### Rollback Scenario 1: Rolling Back from v1.x to v0.9.0

**When to use**: If v1.x deployment has critical issues with pixel statistics or validation features.

**Step 1: Stop New Deployments**

```bash
# Stop any running v1.x functions
vast function stop exr-inspector

# Verify function is stopped
vast function status exr-inspector
```

**Step 2: Backup Current Database State**

```bash
# Create backup of current schema
python scripts/backup_schema.py \
    --endpoint s3.us-east-1.vastdata.com \
    --schema exr_metadata \
    --backup-path s3://backups/exr_metadata_v1_x_backup_2026-02-06.tar.gz

# Verify backup
ls -lh s3://backups/exr_metadata_v1_x_backup_2026-02-06.tar.gz
```

**Step 3: Redeploy v0.9.0 Code**

```bash
# Build v0.9.0 container image
vastde functions build exr-inspector \
    --target ~/functions/exr_inspector \
    --image-tag exr-inspector:v0.9.0

# Tag for registry
docker tag exr-inspector:v0.9.0 \
    CONTAINER_REGISTRY/exr-inspector:v0.9.0

# Push to registry
docker push CONTAINER_REGISTRY/exr-inspector:v0.9.0

# Update function to use v0.9.0 image
vast function update exr-inspector \
    --image CONTAINER_REGISTRY/exr-inspector:v0.9.0

# Verify deployment
vast function logs exr-inspector --tail 20
```

**Step 4: Verify Rollback**

```bash
# Test function with sample EXR file
python -c "
import requests
response = requests.post(
    'https://your-vast-endpoint.example.com/functions/exr-inspector',
    json={'data': {'file_path': '/test.exr'}}
)
assert response.status_code == 200
assert response.json()['schema_version'] == 1
print('✓ Rollback verification passed')
"

# Check function logs for errors
vast function logs exr-inspector --tail 50
```

**Step 5: Restore Database (if needed)**

If database was corrupted during v1.x deployment:

```bash
# Stop function (again, to ensure no writes)
vast function stop exr-inspector

# Restore from backup
python scripts/restore_schema.py \
    --endpoint s3.us-east-1.vastdata.com \
    --schema exr_metadata \
    --backup-path s3://backups/exr_metadata_v1_0_backup_2026-02-06.tar.gz

# Verify restore
python scripts/verify_schema.py \
    --endpoint s3.us-east-1.vastdata.com \
    --schema exr_metadata

# Restart function
vast function start exr-inspector
```

---

### Rollback Scenario 2: Rolling Back from v0.9.1 to v0.9.0

**When to use**: If a patch release (v0.9.1) introduces bugs, roll back to v0.9.0.

**Key Difference**: No database schema changes between patch versions, so rollback is simpler.

**Step 1: Stop Function**

```bash
vast function stop exr-inspector
```

**Step 2: Redeploy v0.9.0 Code**

```bash
# Build v0.9.0 image
vastde functions build exr-inspector \
    --target ~/functions/exr_inspector \
    --image-tag exr-inspector:v0.9.0

docker tag exr-inspector:v0.9.0 CONTAINER_REGISTRY/exr-inspector:v0.9.0
docker push CONTAINER_REGISTRY/exr-inspector:v0.9.0

# Update function
vast function update exr-inspector \
    --image CONTAINER_REGISTRY/exr-inspector:v0.9.0

# Restart
vast function start exr-inspector
```

**Step 3: Verify**

```bash
# Test function
python scripts/test_function.py --version v0.9.0
```

**No database restore needed**: The database schema is identical, so data remains intact.

---

### Rollback Scenario 3: Partial Rollback (Schema Revert)

**When to use**: If migration to v1.1 created new tables that cause performance issues, but you want to keep v0.9.0 data intact.

**Step 1: Drop New Tables (Keep Old Data)**

```bash
# Connect to database
vast db connect exr_metadata

# Drop new v1.1 tables (keep v0.9.0 tables)
DROP TABLE IF EXISTS exr_metadata.pixel_stats;
DROP TABLE IF EXISTS exr_metadata.validation_results;

# Verify old tables still exist
SELECT * FROM exr_metadata.files LIMIT 1;
SELECT * FROM exr_metadata.channels LIMIT 1;
```

**Step 2: Redeploy v0.9.0 Code**

```bash
# Code rollback (same as Scenario 2)
vast function update exr-inspector \
    --image CONTAINER_REGISTRY/exr-inspector:v0.9.0
vast function start exr-inspector
```

**Step 3: Verify**

```bash
# All v0.9.0 data is still available
python scripts/verify_schema.py \
    --endpoint s3.us-east-1.vastdata.com \
    --schema exr_metadata \
    --expected-tables files,parts,channels,attributes
```

**Benefit**: You can later re-enable v1.1 without re-inspecting all files (if tables are restored).

---

### Data Persistence During Rollback

#### What Persists

**Always preserved**:
- All files table data (path, size, mtime, metadata, embeddings)
- All parts table data (multipart structures)
- All channels table data (channel definitions)
- All attributes table data (custom EXR attributes)

**Conditionally preserved** (depending on rollback method):
- New v1.1 tables (pixel_stats, validation_results) — dropped in schema revert, kept in full backup restore
- Embeddings and fingerprints — always preserved in v0.9.0+ schema

#### Data Loss Prevention

```python
# Before dropping tables, export to archive
def archive_before_rollback(session, schema):
    """Export v1.1 tables to Parquet before dropping."""

    # Export pixel_stats
    session.execute(f"""
    COPY (SELECT * FROM {schema}.pixel_stats)
    TO PARQUET 's3://backups/pixel_stats_archive_2026-02-06.parquet'
    """)

    # Export validation_results
    session.execute(f"""
    COPY (SELECT * FROM {schema}.validation_results)
    TO PARQUET 's3://backups/validation_results_archive_2026-02-06.parquet'
    """)

    logger.info("✓ v1.1 tables archived to S3")
```

---

### Testing Rollback in Staging

Before rolling back production, test the procedure:

**Step 1: Clone Production Schema to Staging**

```bash
python scripts/copy_sample_data.py \
    --source-schema exr_metadata \
    --target-schema exr_metadata_staging \
    --sample-size 100
```

**Step 2: Simulate v1.1 Deployment on Staging**

```bash
# Migrate staging to v1.1
python scripts/migrate_v1_0_to_v1_1.py \
    --schema exr_metadata_staging

# Insert some test pixel_stats
python scripts/insert_test_stats.py \
    --schema exr_metadata_staging \
    --file-count 100
```

**Step 3: Test Rollback**

```bash
# Verify current state
python scripts/verify_schema.py --schema exr_metadata_staging

# Perform rollback (drop v1.1 tables)
python scripts/rollback_v1_1.py \
    --schema exr_metadata_staging \
    --archive-tables

# Verify v0.9.0 state
python scripts/verify_schema.py --schema exr_metadata_staging

# Confirm v0.9.0 data still intact
python scripts/data_integrity_check.py \
    --schema exr_metadata_staging
```

**Step 4: Verify Deployment Code Works**

```bash
# Deploy v0.9.0 code
vast function update exr-inspector \
    --image CONTAINER_REGISTRY/exr-inspector:v0.9.0

# Test with staging data
python scripts/test_function.py \
    --schema exr_metadata_staging \
    --sample-files 10
```

---

### Rollback Checklist

Before rolling back production:

- [ ] Identified root cause of issue
- [ ] Determined rollback scenario (code only, schema revert, or full restore)
- [ ] Created backup of current state
- [ ] Tested rollback procedure on staging schema
- [ ] Scheduled maintenance window (off-peak hours)
- [ ] Notified team members
- [ ] Have v0.9.0 container image ready
- [ ] Have database restore script ready (if needed)
- [ ] Document rollback reason and completion

---

### Post-Rollback Verification Checklist

After rolling back:

- [ ] Function is running and responsive
- [ ] Sample EXR files are processed correctly
- [ ] Database integrity verified (row counts, constraints)
- [ ] No errors in function logs
- [ ] Vector embeddings still present in database
- [ ] Can successfully query VAST DataBase
- [ ] Team confirmed issue is resolved

---

### Contacting Support During Rollback

If issues arise during rollback:

1. **Stop function immediately**: `vast function stop exr-inspector`
2. **Do not attempt recovery**: Call for help first
3. **Preserve logs**: `vast function logs exr-inspector > rollback_issue.log`
4. **Restore from backup**: If uncertain, restore from backup
5. **Document issue**: Include logs, timestamps, and actions taken

---

## See Also

- [VECTOR_STRATEGY.md](VECTOR_STRATEGY.md) - Embedding computation details
- [SERVERLESS_INTEGRATION.md](SERVERLESS_INTEGRATION.md) - DataEngine setup
- [VAST_ANALYTICS_QUERIES.md](VAST_ANALYTICS_QUERIES.md) - Query examples
- [SCHEMA_EVOLUTION.md](SCHEMA_EVOLUTION.md) - Schema management
- [SCHEMA_MIGRATION_STRATEGY.md](SCHEMA_MIGRATION_STRATEGY.md) - Migration procedures
- [DEPRECATION_POLICY.md](DEPRECATION_POLICY.md) - API stability commitment
