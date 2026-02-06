# VAST DataBase Schema and Deployment Guide

## Database Schema Definition

This document provides the complete schema for VAST DataBase tables used by exr-inspector persistence layer.

### Prerequisites

- VAST DataBase cluster (v2.x or later)
- S3 endpoint configured
- AWS IAM credentials with S3 access
- Python VASTDB SDK v1.0+

### Schema Creation

Create the following tables in your VAST DataBase. Choose the appropriate SQL dialect for your cluster.

#### 1. Files Table (Parent)

```sql
CREATE TABLE IF NOT EXISTS exr_metadata.files (
    -- Identifiers
    file_id VARCHAR(64) PRIMARY KEY,
    file_path VARCHAR(2048) NOT NULL,
    file_path_normalized VARCHAR(2048) NOT NULL,
    header_hash VARCHAR(64) NOT NULL,

    -- Deduplication constraint (enforce idempotent upsert)
    UNIQUE (file_path_normalized, header_hash),

    -- Metadata
    size_bytes INT64,
    mtime VARCHAR(32),  -- ISO8601 timestamp
    multipart_count INT32,
    is_deep BOOLEAN,

    -- Vector Embedding (384 dimensions)
    metadata_embedding ARRAY<FLOAT32>,

    -- Audit fields
    inspection_timestamp VARCHAR(32),  -- ISO8601
    inspection_count INT32 DEFAULT 1,
    last_inspected VARCHAR(32),  -- ISO8601

    -- Indices for common queries
    INDEX idx_file_path (file_path),
    INDEX idx_normalized_path (file_path_normalized),
    INDEX idx_last_inspected (last_inspected),
);
```

#### 2. Parts Table (Child of files)

```sql
CREATE TABLE IF NOT EXISTS exr_metadata.parts (
    -- Identifiers
    file_id VARCHAR(64) NOT NULL,
    FOREIGN KEY (file_id) REFERENCES files(file_id),

    file_path VARCHAR(2048) NOT NULL,
    part_index INT32 NOT NULL,

    -- Part metadata
    part_name VARCHAR(256),
    view_name VARCHAR(256),
    multi_view BOOLEAN,

    -- Windows (stored as JSON strings)
    data_window VARCHAR(512),
    display_window VARCHAR(512),

    -- Image properties
    pixel_aspect_ratio FLOAT32,
    line_order VARCHAR(32),
    compression VARCHAR(32),

    -- Tiling
    is_tiled BOOLEAN,
    tile_width INT32,
    tile_height INT32,
    tile_depth INT32,

    -- Depth
    is_deep BOOLEAN,

    -- Indices
    PRIMARY KEY (file_id, part_index),
    INDEX idx_compression (compression),
    INDEX idx_is_deep (is_deep),
    INDEX idx_is_tiled (is_tiled),
);
```

#### 3. Channels Table (Child of files)

```sql
CREATE TABLE IF NOT EXISTS exr_metadata.channels (
    -- Identifiers
    file_id VARCHAR(64) NOT NULL,
    FOREIGN KEY (file_id) REFERENCES files(file_id),

    file_path VARCHAR(2048) NOT NULL,
    part_index INT32 NOT NULL,

    -- Channel metadata
    channel_name VARCHAR(256) NOT NULL,
    channel_type VARCHAR(64),

    -- Sampling
    x_sampling INT32,
    y_sampling INT32,

    -- Vector Embedding (128 dimensions, stored in first row only)
    channel_fingerprint ARRAY<FLOAT32>,

    -- Indices
    PRIMARY KEY (file_id, part_index, channel_name),
    INDEX idx_channel_name (channel_name),
    INDEX idx_channel_type (channel_type),
);
```

#### 4. Attributes Table (Child of files)

```sql
CREATE TABLE IF NOT EXISTS exr_metadata.attributes (
    -- Identifiers
    file_id VARCHAR(64) NOT NULL,
    FOREIGN KEY (file_id) REFERENCES files(file_id),

    file_path VARCHAR(2048) NOT NULL,
    part_index INT32,  -- NULL for file-level attributes

    -- Attribute metadata
    attribute_name VARCHAR(256) NOT NULL,
    attribute_type VARCHAR(64),
    attribute_value VARCHAR(4096),  -- JSON serialized

    -- Indices
    PRIMARY KEY (file_id, part_index, attribute_name),
    INDEX idx_attribute_name (attribute_name),
    INDEX idx_attribute_type (attribute_type),
);
```

### Index Strategy

#### Primary Indices
- `files.file_id`: PK for deduplication
- `files.file_path_normalized + files.header_hash`: UNIQUE constraint for idempotent upsert
- `parts.file_id + parts.part_index`: Identifies part within file
- `channels.file_id + channels.part_index + channels.channel_name`: Unique channel
- `attributes.file_id + attributes.part_index + attributes.attribute_name`: Unique attribute

#### Performance Indices
- `files.last_inspected`: Range queries for "files inspected since..."
- `parts.compression`: Analytics on compression usage
- `channels.channel_name`: Find files with specific channels
- `attributes.attribute_name`: Find files with specific attributes

### Query Optimization

For large datasets, consider:

```sql
-- Partition files by mtime for faster range queries
PARTITION files BY RANGE (mtime) (
    PARTITION p_2024 VALUES LESS THAN ('2025-01-01'),
    PARTITION p_2025 VALUES LESS THAN ('2026-01-01'),
);

-- Cluster parts by file_id for join performance
CLUSTER parts BY (file_id);

-- Create materialized views for common aggregations
CREATE MATERIALIZED VIEW compression_stats AS
SELECT
    compression,
    COUNT(DISTINCT file_id) as file_count,
    COUNT(*) as part_count,
    AVG(is_tiled::INT) as tiling_ratio
FROM parts
GROUP BY compression;
```

## Deployment Checklist

### Pre-Deployment

- [ ] VAST DataBase cluster is running and accessible
- [ ] S3 endpoint is configured and reachable
- [ ] IAM credentials have S3 access
- [ ] Network connectivity verified (VPC rules, security groups)
- [ ] DNS resolves correctly (e.g., `s3.vastdata.com`)
- [ ] Certificate/TLS is properly configured (if using HTTPS)

### Database Setup

- [ ] Create schema: `exr_metadata` (or custom via `VAST_DB_SCHEMA`)
- [ ] Create all 4 tables using SQL scripts above
- [ ] Verify unique constraints are enforced
- [ ] Verify foreign key relationships work
- [ ] Test INSERT operations succeed
- [ ] Test SELECT with WHERE clause returns results

### Environment Configuration

#### For Local Development

```bash
# .env or shell profile
export VAST_DB_ENDPOINT="s3.vastdata.com"
export VAST_DB_REGION="us-east-1"
export VAST_DB_ACCESS_KEY="YOUR_ACCESS_KEY"
export VAST_DB_SECRET_KEY="YOUR_SECRET_KEY"
export VAST_DB_SCHEMA="exr_metadata"
```

#### For DataEngine Function

Create a `.env` file or pass via deployment configuration:

```yaml
# deploy.yaml (DataEngine config)
function:
  name: exr-inspector
  environment:
    VAST_DB_ENDPOINT: "s3.vastdata.com"
    VAST_DB_REGION: "us-east-1"
    VAST_DB_ACCESS_KEY: "${SECRET_VASTDB_KEY}"
    VAST_DB_SECRET_KEY: "${SECRET_VASTDB_SECRET}"
    VAST_DB_SCHEMA: "exr_metadata"
```

### Application Deployment

- [ ] Install dependencies: `pip install pyarrow vastdb-sdk`
- [ ] Add to `requirements.txt` in function directory
- [ ] Update Docker image to include VAST SDK
- [ ] Test import: `from vast_db_persistence import persist_to_vast_database`
- [ ] Run unit tests: `python -m pytest test_vast_db_persistence.py`
- [ ] Verify embeddings are computed correctly
- [ ] Test with mock session first

### Integration Testing

#### 1. Test Embedding Computation

```python
from vast_db_persistence import compute_metadata_embedding

payload = {
    "file": {"multipart_count": 1, "is_deep": False},
    "channels": [{"name": "R", "type": "float"}],
    "parts": [{"compression": "zip"}],
}

embedding = compute_metadata_embedding(payload)
assert len(embedding) == 384
assert abs(sum(v*v for v in embedding)**0.5 - 1.0) < 1e-5
```

#### 2. Test Mock Persistence

```python
from unittest.mock import MagicMock
from vast_db_persistence import persist_to_vast_database

mock_session = MagicMock()
mock_session.begin.return_value = mock_session
mock_session.table.return_value = MagicMock()
mock_session.table().select.return_value = None

result = persist_to_vast_database(payload, {}, mock_session)
assert result["status"] == "success"
assert result["inserted"] == True
```

#### 3. Test Against VAST Cluster

```bash
# Set credentials
export VAST_DB_ENDPOINT="s3.cluster.vastdata.com"
export VAST_DB_ACCESS_KEY="..."
export VAST_DB_SECRET_KEY="..."

# Run inspection
python -c "
from functions.exr_inspector.main import handler
result = handler(None, {
    'data': {
        'path': '/test/data/sample.exr',
        'meta': True
    }
})
if result.get('persistence', {}).get('status') == 'success':
    print(f\"SUCCESS: File {result['persistence']['file_id']} persisted\")
else:
    print(f\"ERROR: {result.get('persistence', {}).get('error')}\")
"
```

### Verification Queries

After deployment, verify data is being persisted:

```sql
-- Check recent inspections
SELECT file_id, file_path, last_inspected, inspection_count
FROM exr_metadata.files
ORDER BY last_inspected DESC
LIMIT 10;

-- Verify embeddings are stored
SELECT file_id, array_length(metadata_embedding) as emb_dim
FROM exr_metadata.files
WHERE metadata_embedding IS NOT NULL
LIMIT 5;

-- Check part distribution
SELECT compression, COUNT(*) as count
FROM exr_metadata.parts
GROUP BY compression;

-- Verify channel data
SELECT channel_name, COUNT(DISTINCT file_id) as files_with_channel
FROM exr_metadata.channels
GROUP BY channel_name
ORDER BY files_with_channel DESC;
```

## Performance Tuning

### Connection Pooling

For higher throughput, consider connection pooling:

```python
from vast_db_persistence import Session

# Reuse session across multiple calls (within same container)
session = Session(
    endpoint=endpoint,
    access_key=access_key,
    secret_key=secret_key,
    pool_size=10,  # Connection pool size
)
```

### Batch Operations

Queue multiple files for batch insert:

```python
# Pseudo-code for batch persistence
def batch_persist(payloads, session, batch_size=100):
    results = []
    for i in range(0, len(payloads), batch_size):
        batch = payloads[i:i+batch_size]
        # Start single transaction for batch
        txn = session.begin()
        try:
            for payload in batch:
                # Persist each payload
                pass
            txn.commit()
            results.extend([{"status": "success"} for _ in batch])
        except Exception as e:
            txn.rollback()
            results.extend([{"status": "error", "error": str(e)} for _ in batch])
    return results
```

### Query Performance

Typical query latencies (after deployment):

| Operation | Latency |
|-----------|---------|
| SELECT single file | 10-20ms |
| INSERT 1 file record | 50-100ms |
| Vector distance query (1000 files) | 200-500ms |
| Aggregation (count by compression) | 100-300ms |
| Range query (last 7 days) | 150-400ms |

Factors affecting latency:
- Network distance to VAST endpoint
- Index efficiency (full table scan vs index scan)
- Data size and row count
- Concurrent load on cluster

## Troubleshooting Deployment

### Issue: Connection Timeout

```
timeout: Failed to create VAST DataBase session
```

**Solution**:
- Check endpoint DNS resolves: `nslookup s3.vastdata.com`
- Verify network connectivity: `curl https://s3.vastdata.com`
- Check security group rules allow port 443/8443
- Verify VPC route tables and NAT gateways

### Issue: Authentication Failed

```
Invalid credentials: Access key not found or secret key mismatch
```

**Solution**:
- Verify AWS IAM credentials are correct
- Check credentials have S3 access policy
- Verify environment variables are set correctly
- Test with AWS CLI: `aws s3 ls --endpoint-url https://s3.vastdata.com`

### Issue: Schema Not Found

```
Table not found: exr_metadata.files
```

**Solution**:
- Create schema: `CREATE SCHEMA exr_metadata`
- Create all tables using SQL scripts in this guide
- Verify schema and table names match `VAST_DB_SCHEMA` env var
- Check that persistence code runs after tables exist

### Issue: Unique Constraint Violation

```
Duplicate key value violates unique constraint
```

**Note**: This is NOT an error - it's normal idempotent behavior. The code detects this and returns `inserted=false`, `status=success`.

If you see persistent violations with different file contents:
- Check that `file_path_normalized` normalization is consistent
- Verify `header_hash` is computed correctly from file structure
- Consider if files are truly identical (same content, different paths)

### Issue: Transaction Rollback

```
Transaction failed: Insert failed
```

**Solution**:
- Check foreign key constraints
- Verify all required columns have values
- Check data type mismatches (e.g., INT32 vs INT64)
- Review error logs for specific constraint violation
- Test INSERT directly in SQL console

## Monitoring and Observability

### Logging Configuration

```python
import logging

# Enable debug logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger('vast_db_persistence')
logger.setLevel(logging.DEBUG)
```

### Key Metrics to Monitor

1. **Persistence Success Rate**
   ```sql
   SELECT
       DATE_TRUNC('hour', inspection_timestamp) as hour,
       COUNT(*) as total,
       SUM(CASE WHEN inspection_count = 1 THEN 1 ELSE 0 END) as new_files
   FROM exr_metadata.files
   GROUP BY hour
   ORDER BY hour DESC;
   ```

2. **File Size Distribution**
   ```sql
   SELECT
       PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY size_bytes) as median,
       PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY size_bytes) as p95,
       PERCENTILE_CONT(0.99) WITHIN GROUP (ORDER BY size_bytes) as p99
   FROM exr_metadata.files;
   ```

3. **Compression Usage**
   ```sql
   SELECT compression, COUNT(*) as count, SUM(f.size_bytes) as total_size
   FROM exr_metadata.parts p
   JOIN exr_metadata.files f ON p.file_id = f.file_id
   GROUP BY compression;
   ```

## Maintenance

### Regular Tasks

- **Weekly**: Monitor query performance, check for slow queries
- **Monthly**: Analyze storage usage, partition if needed
- **Quarterly**: Update statistics for query optimization
- **Annually**: Archive old data, consider schema changes

### Data Cleanup

Remove old inspection records:

```sql
-- Delete files not inspected in 6 months
DELETE FROM exr_metadata.files
WHERE last_inspected < CURRENT_DATE - INTERVAL '6 months';

-- Cascade deletes child records (if CASCADE is configured)
```

### Backup Strategy

```bash
# Backup schema
vastdb dump exr_metadata > exr_metadata_backup.sql

# Restore schema
vastdb restore < exr_metadata_backup.sql
```

## Next Steps

1. Review the complete integration guide: `/functions/exr_inspector/VAST_DB_INTEGRATION.md`
2. Review main.py integration: `/functions/exr_inspector/main.py`
3. Run unit tests: `python -m pytest test_vast_db_persistence.py -v`
4. Test against VAST cluster in staging environment
5. Deploy to production DataEngine pipeline
