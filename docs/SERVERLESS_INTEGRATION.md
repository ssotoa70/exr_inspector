# Serverless Integration: exr-inspector on VAST DataEngine

## Overview

The exr-inspector tool integrates with VAST DataEngine as a serverless function, automatically inspecting EXR files and persisting metadata with vector embeddings to VAST Database. This document explains the event flow, credential handling, and deployment patterns.

**Architecture**: File upload → DataEngine trigger → exr-inspector execution → VAST persistence

---

## Event Flow Architecture

### Step-by-Step Flow

```
1. File Upload to VAST Storage
   │
   └─> 2. DataEngine Event Trigger (file_created event)
       │
       └─> 3. Invoke exr-inspector Handler (main.py)
           │
           ├─> 4a. Inspect EXR with OpenImageIO
           │       └─> Extract metadata, channels, parts, attributes
           │
           ├─> 4b. Compute Vector Embeddings
           │       └─> metadata_embedding (384D)
           │       └─> channel_fingerprint (128D)
           │
           └─> 4c. Persist to VAST Database
               │
               ├─> Check for existing file (idempotent)
               │
               └─> If new: Insert files, parts, channels, attributes rows
                   └─> If exists: Skip (or update audit fields)
       │
       └─> 5. Return Inspection Result
           │
           └─> Result includes:
               - Status (success/error/skipped)
               - file_id (unique identifier)
               - inserted (bool: new or existing)
               - persistence details
```

### Event Payload Structure

DataEngine passes an event object to the handler:

```python
event = {
    "data": {
        "path": "/renders/shot_001/beauty.0001.exr",  # File path (required)
        "meta": True,              # Enable metadata extraction (default: True)
        "stats": False,            # Enable pixel stats (default: False)
        "deep_stats": False,       # Enable deep data stats (default: False)
        "validate": False,         # Enable validation checks (default: False)
        "policy_path": None,       # Path to validation policy (optional)
    },
    # Credentials passed from DataEngine (optional)
    "vastdb_endpoint": "https://vast-db.example.com",
    "vastdb_access_key": "abc123...",
    "vastdb_secret_key": "xyz789...",
    "vastdb_region": "us-east-1",
}
```

---

## Credential Handling

### Credential Priority

The persistence layer uses this priority for finding credentials:

```
1. Event context (passed from DataEngine)
   ├─> event.get("vastdb_endpoint")
   ├─> event.get("vastdb_access_key")
   ├─> event.get("vastdb_secret_key")
   ├─> event.get("vastdb_region")
   │
2. Environment variables
   ├─> os.environ.get("VAST_DB_ENDPOINT")
   ├─> os.environ.get("VAST_DB_ACCESS_KEY")
   ├─> os.environ.get("VAST_DB_SECRET_KEY")
   ├─> os.environ.get("VAST_DB_REGION")
   │
3. Default configuration
   └─> VAST_DB_REGION defaults to "us-east-1"
```

See `vast_db_persistence.py` lines 669-729 for implementation.

### Setting Up Credentials

#### Option 1: DataEngine Event Context (Recommended)

DataEngine automatically injects credentials into the event when triggered from within VAST infrastructure:

```python
# In DataEngine configuration
event_config = {
    "inject_credentials": True,  # VAST auto-injects credentials
}
```

**No additional setup needed** - credentials flow from DataEngine to handler.

#### Option 2: Environment Variables

For development or explicit configuration:

```bash
# Set in DataEngine runtime environment
export VAST_DB_ENDPOINT="https://vast-db-us-east-1.example.com"
export VAST_DB_ACCESS_KEY="your-access-key"
export VAST_DB_SECRET_KEY="your-secret-key"
export VAST_DB_REGION="us-east-1"

# Or in serverless config
serverless:
  environment:
    VAST_DB_ENDPOINT: "https://vast-db-us-east-1.example.com"
    VAST_DB_ACCESS_KEY: ${env:VAST_DB_ACCESS_KEY}
    VAST_DB_SECRET_KEY: ${env:VAST_DB_SECRET_KEY}
```

#### Option 3: Schema Configuration

Set VAST_DB_SCHEMA env var for custom schema name (default: `exr_metadata`):

```bash
export VAST_DB_SCHEMA="exr_metadata_prod"  # Use custom schema
```

### Credential Security Best Practices

1. **Never commit credentials** to version control
2. **Use secret management**: AWS Secrets Manager, HashiCorp Vault, etc.
3. **Rotate access keys** regularly (quarterly minimum)
4. **Audit credential access** - log who/when credentials are used
5. **Use IAM roles** instead of static credentials when possible
6. **Scope credentials** - limit permissions to VAST Database only
7. **Test credentials** before deployment

---

## Error Handling and Retries

### Error Categories

| Category | Cause | Handler Behavior | Retry |
|----------|-------|------------------|-------|
| **File Not Found** | Missing input file | Returns error in result | Manual |
| **Vector Embedding** | Invalid metadata structure | Returns error, logs exception | No |
| **Connection Error** | VAST endpoint unreachable | Returns error, logs with endpoint | Yes (3x) |
| **Authentication** | Invalid credentials | Returns error, logs failure | No |
| **Transaction Failure** | Database error during insert | Rollback, returns error | Yes (1x) |
| **Not Configured** | No VAST credentials available | Returns "skipped", logs debug | No |

### Error Result Structure

When an error occurs, the handler returns:

```python
{
    "status": "error",  # or "success", "skipped"
    "message": "Human-readable message",
    "error": "Detailed error description",
    "file_id": None,  # Only set on success
    "inserted": False,
}
```

### Retry Strategy

#### Automatic Retries (Built-in)

```python
# In persist_to_vast_database():
try:
    session = _create_vastdb_session(event)
    # ... perform operations ...
except VASTDatabaseError as exc:
    # Log error, return error status
    result["error"] = str(exc)
    return result
```

The handler does NOT automatically retry - it returns error status immediately.

#### Recommended: DataEngine-Level Retries

Configure DataEngine to retry failed invocations:

```yaml
# DataEngine trigger configuration
function:
  name: exr-inspector
  runtime: python3.9
  triggers:
    - type: s3  # or your storage trigger type
      events:
        - s3:ObjectCreated:*
      retry:
        max_attempts: 3
        backoff_seconds: 60  # Exponential backoff
        max_backoff_seconds: 300
```

#### Manual Retry Pattern

For production systems, implement exponential backoff:

```python
import time
import random

def invoke_with_retries(event: dict, max_retries: int = 3) -> dict:
    for attempt in range(max_retries):
        try:
            result = handler(ctx, event)
            if result["status"] != "error":
                return result
        except Exception as exc:
            if attempt < max_retries - 1:
                backoff = (2 ** attempt) + random.uniform(0, 1)
                logger.warning(
                    f"Attempt {attempt + 1} failed, retrying in {backoff:.1f}s: {exc}"
                )
                time.sleep(backoff)
            else:
                logger.error(f"All {max_retries} attempts failed")
                raise
    return result
```

### Transaction Rollback

On database error, the transaction is automatically rolled back:

```python
# In _persist_with_transaction():
try:
    txn = session.begin()
    # ... insert operations ...
    txn.commit()
except Exception as exc:
    if txn:
        try:
            txn.rollback()  # Automatic rollback on error
            logger.debug(f"Transaction rolled back for {file_id}")
        except Exception as rollback_exc:
            logger.warning(f"Rollback failed: {rollback_exc}")
    raise
```

---

## Monitoring and Logging

### Logger Configuration

The module uses Python's standard logging:

```python
logger = logging.getLogger(__name__)
```

### Log Levels

| Level | Message Type | Example |
|-------|--------------|---------|
| **DEBUG** | Operation flow | "Computing embeddings for /data/test.exr" |
| **INFO** | Success events | "File inserted: abc123..." |
| **WARNING** | Non-blocking issues | "SELECT query failed: ..." |
| **ERROR** | Failures | "Failed to compute metadata embedding: ..." |
| **EXCEPTION** | Unhandled errors | Full traceback |

### Key Log Points

```python
# Session creation
logger.info(f"VAST DataBase session created: {endpoint}")
logger.warning("vastdb_sdk not available; skipping persistence")
logger.debug("VAST_DB_ENDPOINT not configured")

# Embedding computation
logger.debug(f"Computing embeddings for {file_path}")
logger.error(result["error"])  # On embedding failure

# Persistence
logger.debug(f"Transaction started for {file_id}")
logger.info(f"File inserted: {file_id}")
logger.info(f"File exists (idempotent): {file_id}")

# Transaction handling
logger.debug(f"Transaction rolled back for {file_id}")
logger.warning(f"Rollback failed: {rollback_exc}")
```

### Enabling Debug Logging

In your handler initialization:

```python
import logging

# Enable debug logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Or configure specific loggers
logging.getLogger('vast_db_persistence').setLevel(logging.DEBUG)
```

### CloudWatch Integration (AWS)

In DataEngine, logs automatically flow to CloudWatch:

```bash
# View logs in real-time
aws logs tail /aws/lambda/exr-inspector --follow

# Filter for errors
aws logs filter-log-events \
    --log-group-name /aws/lambda/exr-inspector \
    --filter-pattern "ERROR"

# Get statistics
aws logs describe-log-groups | grep exr-inspector
```

### Custom Metrics

To add custom monitoring:

```python
from cloudwatch import CloudWatch

def handler(ctx, event):
    try:
        result = _inspect_and_persist(event)

        # Record success metric
        CloudWatch.put_metric_data(
            Namespace='exr-inspector',
            MetricData=[
                {
                    'MetricName': 'SuccessfulInspections',
                    'Value': 1,
                    'Unit': 'Count'
                }
            ]
        )
        return result

    except Exception as exc:
        # Record error metric
        CloudWatch.put_metric_data(
            Namespace='exr-inspector',
            MetricData=[
                {
                    'MetricName': 'InspectionErrors',
                    'Value': 1,
                    'Unit': 'Count'
                }
            ]
        )
        raise
```

---

## Testing Locally vs VAST Cluster

### Local Testing (Development)

#### Setup

```bash
# 1. Install dependencies
pip install pyarrow vastdb_sdk openimageio

# 2. Set credentials
export VAST_DB_ENDPOINT="https://vast-cluster.example.com"
export VAST_DB_ACCESS_KEY="test-key"
export VAST_DB_SECRET_KEY="test-secret"

# 3. Create test schema (one-time)
python -m vast_db_persistence create-schema
```

#### Test Payload

```python
# test_local.py
import json
from functions.exr_inspector.main import handler

# Mock context object
class MockContext:
    pass

# Minimal event
event = {
    "data": {
        "path": "/path/to/test.exr",
        "meta": True,
    }
}

# Run handler
result = handler(MockContext(), event)
print(json.dumps(result, indent=2))
```

#### Run Tests

```bash
python test_local.py
# Output:
# {
#   "status": "success",
#   "file_id": "abc123...",
#   "inserted": true,
#   "persistence": {
#     "status": "success",
#     "file_id": "abc123..."
#   },
#   ...
# }
```

### Unit Tests

Comprehensive tests in `test_vast_db_persistence.py`:

```bash
# Run all tests
python -m pytest test_vast_db_persistence.py -v

# Run specific test
python -m pytest test_vast_db_persistence.py::TestVectorEmbeddings -v

# With coverage
python -m pytest test_vast_db_persistence.py --cov=vast_db_persistence --cov-report=html
```

### Testing on VAST Cluster

#### Deploy to DataEngine

```bash
# 1. Package function
zip -r exr-inspector.zip functions/exr_inspector/

# 2. Upload to DataEngine
vast function deploy \
    --name exr-inspector \
    --runtime python3.9 \
    --handler main.handler \
    --source exr-inspector.zip

# 3. Configure trigger
vast function trigger create \
    --function exr-inspector \
    --source s3 \
    --bucket renders \
    --event ObjectCreated
```

#### Invoke Test

```bash
# Invoke synchronously with test event
vast function invoke exr-inspector \
    --payload '{
        "data": {
            "path": "/renders/test.exr",
            "meta": true
        }
    }'
```

#### Monitor Execution

```bash
# View logs
vast function logs exr-inspector --tail

# View invocation metrics
vast function metrics exr-inspector --duration 1h

# Check persistence results
psql -h vast-db.example.com << EOF
SELECT COUNT(*) FROM exr_metadata.files;
SELECT COUNT(*) FROM exr_metadata.channels;
EOF
```

---

## Deployment Checklist

### Pre-Deployment

- [ ] All tests passing (`pytest test_vast_db_persistence.py`)
- [ ] Code reviewed and approved
- [ ] Dependencies pinned to specific versions
- [ ] Credentials configured (not committed)
- [ ] VAST Database schema created (`exr_metadata`)
- [ ] Schema tables initialized (files, parts, channels, attributes)
- [ ] Vector dimensions match code (metadata: 384D, channels: 128D)

### Deployment

- [ ] Package function with all dependencies
- [ ] Deploy to staging DataEngine first
- [ ] Test with sample EXR file
- [ ] Verify records inserted in VAST Database
- [ ] Check CloudWatch/DataEngine logs for errors
- [ ] Run analytics queries to verify data quality
- [ ] Deploy to production DataEngine
- [ ] Configure production file upload triggers
- [ ] Set up monitoring alerts

### Post-Deployment

- [ ] Monitor first 24 hours of executions
- [ ] Verify persistence rate (should be >99%)
- [ ] Check for embedding computation errors
- [ ] Validate vector quality (embeddings normalized to 1.0)
- [ ] Run daily analytics queries
- [ ] Set up automated backups of VAST Database
- [ ] Document any deviations from standard setup

### Rollback Plan

If issues occur post-deployment:

```bash
# 1. Disable DataEngine trigger
vast function trigger disable exr-inspector

# 2. Revert to previous version
vast function deploy \
    --name exr-inspector \
    --version v1.2.3  # Previous version

# 3. Re-enable trigger
vast function trigger enable exr-inspector

# 4. Investigate issue
vast function logs exr-inspector --start 2025-02-05T10:00:00Z
```

### Rollback Database

If data corruption detected:

```bash
# 1. Backup current state
pg_dump -h vast-db.example.com exr_metadata > backup_$(date +%s).sql

# 2. Restore from backup (if available)
psql -h vast-db.example.com < backup_1738763400.sql

# 3. Or drop and recreate schema
psql << EOF
DROP SCHEMA IF EXISTS exr_metadata CASCADE;
-- Re-run table creation
\i schema_init.sql
EOF
```

---

## Performance Considerations

### Serverless Constraints

| Resource | Limit | Impact |
|----------|-------|--------|
| **Memory** | 128 MB - 10 GB | Embedding computation needs <100 MB |
| **Timeout** | 5 min - 1 hour | File inspection: <30 sec typical |
| **Concurrency** | Depends on tier | 100s of concurrent executions supported |
| **Disk** | 512 MB temp | Sufficient for single file inspection |

### Optimization Tips

1. **Vectorization is fast**: Embedding computation <10ms (see VECTOR_STRATEGY.md)
2. **Network is slow**: Database round-trips dominate (100-500ms)
3. **Batch operations**: For bulk processing, collect results and batch insert
4. **Idempotent operations**: Safe to retry without duplicate data
5. **Use read replicas**: For analytics queries, separate from write traffic

### Timeout Configuration

```yaml
# DataEngine function config
function:
  name: exr-inspector
  timeout: 300  # 5 minutes (default)
  memory: 512   # 512 MB (for OpenImageIO + PyArrow)
```

---

## Common Issues and Solutions

| Issue | Cause | Solution |
|-------|-------|----------|
| "No module named 'vastdb_sdk'" | SDK not installed | `pip install vastdb_sdk` |
| "VAST_DB_ENDPOINT not configured" | Missing credentials | Set env var or event context |
| "Failed to create VAST session" | Invalid credentials | Verify endpoint, access_key, secret_key |
| "Vector embedding size mismatch" | Wrong embedding_dim | Verify 384D metadata, 128D channels |
| "Transaction failed: ..." | Database error | Check VAST DB logs, verify schema exists |
| "Slow queries" | No indexes | Create indexes on file_path_normalized, is_deep |

---

## See Also

- [VECTOR_STRATEGY.md](VECTOR_STRATEGY.md) - Embedding computation details
- [VAST_ANALYTICS_QUERIES.md](VAST_ANALYTICS_QUERIES.md) - Example queries
- [SCHEMA_EVOLUTION.md](SCHEMA_EVOLUTION.md) - Schema management
- [TROUBLESHOOTING.md](TROUBLESHOOTING.md) - Detailed troubleshooting guide
