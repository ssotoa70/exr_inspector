# Schema Migration Strategy

## Overview

This document outlines how exr-inspector manages schema evolution, data migrations, and rollback procedures across versions. It covers both the JSON output schema and the VAST DataBase schema.

---

## Schema Versioning Mechanism

### JSON Output Schema

The output includes a schema_version field that clients can use to handle different formats:

```json
{
  "schema_version": 1,
  "file": { ... },
  "parts": [ ... ],
  "channels": [ ... ],
  "attributes": { ... },
  "stats": { ... },
  "validation": { ... },
  "errors": [ ... ]
}
```

**Current Versions**:
- **v1** (v0.9.0 onwards): Initial stable schema with metadata, parts, channels, and attributes

**Future Versions**:
- **v2** (v2.0.0+): May introduce breaking changes (reserved for major version releases)

### VAST DataBase Schema

The database schema is versioned per table using `schema_version` columns:

```python
CREATE TABLE files (
    file_id INT PRIMARY KEY,
    file_path STRING,
    file_path_normalized STRING,
    size_bytes INT,
    mtime TIMESTAMP,
    header_hash STRING,
    metadata_embedding FLOAT VECTOR(384),
    created_at TIMESTAMP,
    updated_at TIMESTAMP,
    schema_version INT DEFAULT 1,  # Schema version tracking
    metadata JSON                   # Reserved for future use
);
```

**Current Versions**:
- **v1** (v0.9.0 onwards): Files, parts, channels, attributes tables with vector embeddings

**Future Versions**:
- **v2** (v1.1.0+): May add pixel_stats, validation_results tables
- Records retain schema_version field to enable gradual migration

---

## v1.0 → v1.1 Migration (Pixel Statistics)

### What Changes in v1.1

Adding pixel statistics requires new database tables:

```python
# New in v1.1
CREATE TABLE pixel_stats (
    stat_id INT PRIMARY KEY,
    file_id INT REFERENCES files(file_id),
    part_index INT,
    channel_name STRING,
    stat_type ENUM('min', 'max', 'mean', 'stddev', 'nan_count', 'inf_count'),
    stat_value FLOAT,
    sampling_rate FLOAT,
    computed_at TIMESTAMP,
    schema_version INT DEFAULT 1,
    created_at TIMESTAMP,
    updated_at TIMESTAMP
);

CREATE TABLE validation_results (
    validation_id INT PRIMARY KEY,
    file_id INT REFERENCES files(file_id),
    rule_name STRING,
    passed BOOLEAN,
    message STRING,
    severity ENUM('info', 'warning', 'error'),
    schema_version INT DEFAULT 1,
    created_at TIMESTAMP,
    updated_at TIMESTAMP
);
```

### JSON Output Schema Changes (v1.1)

**v1.0 Output**:
```json
{
  "schema_version": 1,
  "file": { ... },
  "parts": [ ... ],
  "channels": [ ... ],
  "attributes": { ... },
  "stats": {},
  "validation": {},
  "errors": [ ... ]
}
```

**v1.1 Output** (backward compatible):
```json
{
  "schema_version": 1,
  "file": { ... },
  "parts": [ ... ],
  "channels": [ ... ],
  "attributes": { ... },
  "stats": {
    "enabled": true,
    "sampling_rate": 0.25,
    "channels": [
      {
        "name": "R",
        "min": 0.0,
        "max": 1.0,
        "mean": 0.5,
        "stddev": 0.2,
        "nan_count": 0,
        "inf_count": 0
      }
    ]
  },
  "validation": {},
  "errors": [ ... ]
}
```

**Key Point**: `schema_version` remains 1 because JSON output is backward compatible (new fields added, nothing removed).

### Migration Path

**Phase 1: Dual-Write (v1.0 Deployment)**
```
Timeline: v1.1.0 release date + 2 weeks
Action: Run both old and new code simultaneously
- exr-inspector v1.1 writes to both old schema (v0.9 compatible) and new pixel_stats table
- Database has schema_version=1 records (old) and schema_version=2 records (new)
- No data loss, both code paths active
```

**Phase 2: Validation Window (v1.1 Deployment)**
```
Timeline: 2 weeks to 4 weeks
Action: Monitor and validate pixel statistics
- Compare pixel stats results with reference implementations
- Check database performance with new tables
- Test rollback procedures
- Gather user feedback
```

**Phase 3: Backfill (v1.1 Stable)**
```
Timeline: Week 4-6 of v1.1 release
Action: Compute statistics for previously-scanned files
- See "Backfill Procedures" section below
```

---

## Migration Scripts Approach

### Script Structure

Migration scripts follow a standard pattern:

```python
# scripts/migrate_v1_0_to_v1_1.py

"""
Migration script: v1.0 schema → v1.1 schema

Adds pixel_stats and validation_results tables.
No data loss - old tables remain unchanged.

Usage:
    python scripts/migrate_v1_0_to_v1_1.py \
        --endpoint s3.region.vastdata.com \
        --schema exr_metadata \
        --dry-run              # Preview changes (don't commit)
        --backfill             # Optionally backfill historical data
"""

import argparse
import logging
from vastdb_sdk import Session

logger = logging.getLogger(__name__)

def main(args):
    session = Session(
        endpoint=args.endpoint,
        access_key=os.environ['VAST_DB_ACCESS_KEY'],
        secret_key=os.environ['VAST_DB_SECRET_KEY']
    )

    if args.dry_run:
        preview_migrations(session, args.schema)
    else:
        apply_migrations(session, args.schema)

    if args.backfill:
        backfill_historical_data(session, args.schema)

def preview_migrations(session, schema):
    """Show what would be created."""
    logger.info(f"Would create tables in schema: {schema}")
    logger.info("Table: pixel_stats")
    logger.info("  - stat_id (INT PRIMARY KEY)")
    logger.info("  - file_id (INT, foreign key to files)")
    logger.info("  - channel_name (STRING)")
    # ... more schema preview ...

def apply_migrations(session, schema):
    """Execute migration scripts."""
    txn = session.begin_transaction()
    try:
        # Create new tables
        session.execute(f"""
        CREATE TABLE IF NOT EXISTS {schema}.pixel_stats (
            stat_id INT PRIMARY KEY,
            file_id INT,
            part_index INT,
            channel_name STRING,
            stat_type STRING,
            stat_value FLOAT,
            sampling_rate FLOAT,
            computed_at TIMESTAMP,
            schema_version INT DEFAULT 1,
            created_at TIMESTAMP,
            updated_at TIMESTAMP
        )
        """)

        session.execute(f"""
        CREATE TABLE IF NOT EXISTS {schema}.validation_results (
            validation_id INT PRIMARY KEY,
            file_id INT,
            rule_name STRING,
            passed BOOLEAN,
            message STRING,
            severity STRING,
            schema_version INT DEFAULT 1,
            created_at TIMESTAMP,
            updated_at TIMESTAMP
        )
        """)

        # Create indexes
        session.execute(f"""
        CREATE INDEX IF NOT EXISTS idx_pixel_stats_file
        ON {schema}.pixel_stats(file_id)
        """)

        # Log migration success
        logger.info("Migration completed successfully")
        txn.commit()

    except Exception as e:
        logger.error(f"Migration failed: {e}")
        txn.rollback()
        raise

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Migrate exr-inspector schema')
    parser.add_argument('--endpoint', required=True, help='VAST DB endpoint')
    parser.add_argument('--schema', default='exr_metadata', help='Database schema')
    parser.add_argument('--dry-run', action='store_true', help='Preview changes')
    parser.add_argument('--backfill', action='store_true', help='Backfill historical data')
    args = parser.parse_args()

    main(args)
```

### Migration Execution

```bash
# Preview migration (no changes)
python scripts/migrate_v1_0_to_v1_1.py \
    --endpoint s3.us-east-1.vastdata.com \
    --schema exr_metadata \
    --dry-run

# Apply migration (creates new tables)
python scripts/migrate_v1_0_to_v1_1.py \
    --endpoint s3.us-east-1.vastdata.com \
    --schema exr_metadata

# Apply migration + backfill historical data
python scripts/migrate_v1_0_to_v1_1.py \
    --endpoint s3.us-east-1.vastdata.com \
    --schema exr_metadata \
    --backfill
```

---

## Backfill Procedures Concept

### Purpose

After adding pixel_stats in v1.1, existing files in the database (from v0.9 era) don't have statistics. Backfilling computes and inserts statistics for historical data.

### Backfill Strategy

**Step 1: Identify Files Without Statistics**

```python
def find_unprocessed_files(session, schema, limit=100):
    """Find files that don't have pixel_stats yet."""
    query = f"""
    SELECT f.file_id, f.file_path
    FROM {schema}.files f
    LEFT JOIN {schema}.pixel_stats ps ON f.file_id = ps.file_id
    WHERE ps.file_id IS NULL
    LIMIT {limit}
    """
    return session.execute(query)
```

**Step 2: Retrieve Original Files and Recompute Statistics**

```python
def backfill_pixel_stats(session, schema, file_path):
    """Reprocess file to compute pixel statistics."""
    from exr_inspector.main import handler

    # Simulate original event
    event = {
        "data": {
            "file_path": file_path,
            "enable_stats": True,        # Enable stats computation
            "enable_meta": True,
            "enable_validate": False,
            "enable_deep_stats": False
        }
    }

    # Run inspection with stats enabled
    result = handler(None, event)

    # Extract and store pixel_stats
    if "stats" in result and result["stats"]:
        insert_pixel_stats_from_result(session, schema, result)

    return result
```

**Step 3: Batch Processing**

```python
def backfill_batch(session, schema, batch_size=50, max_batches=None):
    """Process unprocessed files in batches."""
    batch_count = 0

    while True:
        # Find next batch
        unprocessed = find_unprocessed_files(session, schema, limit=batch_size)
        if not unprocessed:
            logger.info(f"Backfill complete. Processed {batch_count * batch_size} files.")
            break

        # Process batch
        for file_record in unprocessed:
            try:
                result = backfill_pixel_stats(session, schema, file_record['file_path'])
                logger.info(f"Processed: {file_record['file_path']}")
            except Exception as e:
                logger.error(f"Failed to process {file_record['file_path']}: {e}")
                # Continue with next file, don't stop entire backfill

        batch_count += 1
        if max_batches and batch_count >= max_batches:
            logger.info(f"Stopping after {max_batches} batches (optional limit reached)")
            break

        # Brief pause between batches to avoid overwhelming database
        time.sleep(0.5)
```

**Step 4: Verification**

```python
def verify_backfill(session, schema):
    """Check that backfill was successful."""
    result = session.execute(f"""
    SELECT
        COUNT(DISTINCT f.file_id) as total_files,
        COUNT(DISTINCT ps.file_id) as files_with_stats,
        ROUND(100.0 * COUNT(DISTINCT ps.file_id) / COUNT(DISTINCT f.file_id), 1) as coverage_pct
    FROM {schema}.files f
    LEFT JOIN {schema}.pixel_stats ps ON f.file_id = ps.file_id
    """)

    for row in result:
        logger.info(f"Total files: {row['total_files']}")
        logger.info(f"Files with stats: {row['files_with_stats']}")
        logger.info(f"Coverage: {row['coverage_pct']}%")
```

### Backfill Execution

```bash
# Run backfill with dry-run (see what would happen)
python scripts/migrate_v1_0_to_v1_1.py \
    --endpoint s3.us-east-1.vastdata.com \
    --schema exr_metadata \
    --backfill \
    --dry-run

# Run backfill for real
python scripts/migrate_v1_0_to_v1_1.py \
    --endpoint s3.us-east-1.vastdata.com \
    --schema exr_metadata \
    --backfill

# Run backfill with limit (process only 500 files)
python scripts/migrate_v1_0_to_v1_1.py \
    --endpoint s3.us-east-1.vastdata.com \
    --schema exr_metadata \
    --backfill \
    --max-files 500
```

---

## Testing Migration in Staging

### Pre-Migration Testing

**1. Clone Schema to Staging**

```bash
# Create staging schema with same structure as production
vast db schema clone \
    --source exr_metadata \
    --target exr_metadata_staging

# Alternatively, manually create
python scripts/setup_schema.py --schema exr_metadata_staging
```

**2. Copy Sample Data**

```bash
# Copy representative sample of production data
python scripts/copy_sample_data.py \
    --source-schema exr_metadata \
    --target-schema exr_metadata_staging \
    --sample-size 1000      # Copy 1000 files
```

**3. Test Migration**

```bash
# Run migration on staging
python scripts/migrate_v1_0_to_v1_1.py \
    --endpoint s3.us-east-1.vastdata.com \
    --schema exr_metadata_staging

# Verify schema
python scripts/verify_schema.py \
    --endpoint s3.us-east-1.vastdata.com \
    --schema exr_metadata_staging
```

### Staging Validation

**1. Data Integrity Checks**

```python
def validate_migration(session, source_schema, target_schema):
    """Validate migration completed successfully."""

    # Check table counts
    source_counts = get_table_counts(session, source_schema)
    target_counts = get_table_counts(session, target_schema)

    assert source_counts['files'] == target_counts['files'], \
        "Files table row count mismatch"
    assert source_counts['channels'] == target_counts['channels'], \
        "Channels table row count mismatch"

    # Check new tables exist
    assert has_table(session, target_schema, 'pixel_stats'), \
        "pixel_stats table not created"
    assert has_table(session, target_schema, 'validation_results'), \
        "validation_results table not created"

    # Check indexes
    assert has_index(session, target_schema, 'pixel_stats', 'idx_pixel_stats_file'), \
        "Index not created on pixel_stats"

    logger.info("✓ Migration validation passed")
```

**2. Performance Testing**

```bash
# Test query performance on staging
python scripts/performance_test.py \
    --schema exr_metadata_staging \
    --queries vector_similarity,channel_filter,attribute_search

# Measure migration time
time python scripts/migrate_v1_0_to_v1_1.py \
    --endpoint s3.us-east-1.vastdata.com \
    --schema exr_metadata_staging
```

**3. Backfill Testing**

```bash
# Test backfill process on staging sample
python scripts/migrate_v1_0_to_v1_1.py \
    --endpoint s3.us-east-1.vastdata.com \
    --schema exr_metadata_staging \
    --backfill \
    --max-files 100    # Test on small sample first

# Verify backfill results
python scripts/verify_backfill.py \
    --endpoint s3.us-east-1.vastdata.com \
    --schema exr_metadata_staging
```

### Production Migration

Only after staging tests pass:

```bash
# 1. Create backup of production schema
python scripts/backup_schema.py \
    --endpoint s3.us-east-1.vastdata.com \
    --schema exr_metadata \
    --backup-path s3://backups/exr_metadata_v1_0_backup_2026-02-06.tar.gz

# 2. Run migration on production (off-peak hours)
python scripts/migrate_v1_0_to_v1_1.py \
    --endpoint s3.us-east-1.vastdata.com \
    --schema exr_metadata

# 3. Verify production
python scripts/verify_schema.py \
    --endpoint s3.us-east-1.vastdata.com \
    --schema exr_metadata

# 4. Monitor for errors
tail -f /var/log/exr-inspector/migration.log
```

---

## Rollback Procedures

### Rollback Scenario 1: Pre-Migration

If problems arise before migration starts:

```bash
# Cancel migration (no data affected yet)
python scripts/migrate_v1_0_to_v1_1.py \
    --endpoint s3.us-east-1.vastdata.com \
    --schema exr_metadata \
    --cancel

# Verify rollback
python scripts/verify_schema.py \
    --endpoint s3.us-east-1.vastdata.com \
    --schema exr_metadata
```

### Rollback Scenario 2: Mid-Migration

If migration fails partway through:

```bash
# Automatic transaction rollback
# (VAST handles this automatically if error occurs)

# Manual verification
python scripts/check_migration_state.py \
    --endpoint s3.us-east-1.vastdata.com \
    --schema exr_metadata

# If needed, restore from backup
python scripts/restore_schema.py \
    --endpoint s3.us-east-1.vastdata.com \
    --schema exr_metadata \
    --backup-path s3://backups/exr_metadata_v1_0_backup_2026-02-06.tar.gz
```

### Rollback Scenario 3: Post-Migration Issues

If new tables cause performance problems:

```bash
# Option 1: Drop new tables (keep schema v1 code active)
python scripts/rollback_v1_1.py \
    --endpoint s3.us-east-1.vastdata.com \
    --schema exr_metadata \
    --drop-pixel-stats \
    --drop-validation-results

# Option 2: Restore from backup (full rollback to v1.0)
python scripts/restore_schema.py \
    --endpoint s3.us-east-1.vastdata.com \
    --schema exr_metadata \
    --backup-path s3://backups/exr_metadata_v1_0_backup_2026-02-06.tar.gz

# Redeploy exr-inspector v1.0 code
vast function update exr-inspector --image-tag exr-inspector:v1.0.0
```

### Rollback Verification

```python
def verify_rollback(session, schema, target_version):
    """Verify rollback to target version succeeded."""

    if target_version == "v1.0":
        # Check that new tables don't exist
        assert not has_table(session, schema, 'pixel_stats'), \
            "pixel_stats table should not exist in v1.0"
        assert not has_table(session, schema, 'validation_results'), \
            "validation_results table should not exist in v1.0"

        # Check that old tables exist
        assert has_table(session, schema, 'files'), \
            "files table missing"
        assert has_table(session, schema, 'channels'), \
            "channels table missing"

    logger.info(f"✓ Rollback to {target_version} verified")
```

---

## Data Persistence During Rollback

### What Happens to Data

**Scenario 1: Rollback before pixel_stats table created**
- All v1.0 data (files, parts, channels, attributes) remains intact
- No new tables to remove
- Database fully usable with v1.0 code

**Scenario 2: Rollback after pixel_stats table created but no backfill**
- New tables (pixel_stats, validation_results) can be dropped
- All v1.0 data (files, parts, channels, attributes) remains intact
- Re-enabling v1.1 code later won't require re-inspection

**Scenario 3: Rollback after backfill completed**
- Historical statistics are lost if tables are dropped
- v1.0 data remains intact
- Re-enabling v1.1 code later requires re-running backfill
- Original files should still be accessible for recomputation

### Data Preservation Strategy

```python
def safe_rollback_v1_1(session, schema, preserve_stats=True):
    """Rollback v1.1 changes while optionally preserving computed stats."""

    if preserve_stats:
        # Export pixel_stats for external storage (archive)
        export_pixel_stats_to_parquet(session, schema,
            output_path="s3://backups/pixel_stats_archive_2026-02-06.parquet")

        logger.info("✓ Pixel statistics exported to archive")

    # Drop new tables
    session.execute(f"DROP TABLE IF EXISTS {schema}.pixel_stats")
    session.execute(f"DROP TABLE IF EXISTS {schema}.validation_results")

    # Verify old tables intact
    assert has_table(session, schema, 'files'), "files table missing after rollback!"
    assert count_rows(session, schema, 'files') > 0, "files table is empty after rollback!"

    logger.info("✓ Rollback to v1.0 schema completed")
```

---

## Testing Rollback in Staging

### Staged Rollback Testing

```bash
# 1. Start with v1.0 staging schema
python scripts/verify_schema.py \
    --schema exr_metadata_staging

# 2. Migrate to v1.1 on staging
python scripts/migrate_v1_0_to_v1_1.py \
    --schema exr_metadata_staging

# 3. Verify v1.1 migration
python scripts/verify_schema.py \
    --schema exr_metadata_staging

# 4. Run backfill on staging
python scripts/migrate_v1_0_to_v1_1.py \
    --schema exr_metadata_staging \
    --backfill \
    --max-files 100

# 5. Test rollback
python scripts/rollback_v1_1.py \
    --schema exr_metadata_staging \
    --preserve-stats

# 6. Verify rollback
python scripts/verify_schema.py \
    --schema exr_metadata_staging

# 7. Confirm v1.0 data still intact
python scripts/data_integrity_check.py \
    --schema exr_metadata_staging \
    --verify-row-counts
```

---

## Summary: Migration Checklist

- [ ] Create migration script (migrate_v1_0_to_v1_1.py)
- [ ] Test migration on staging schema
- [ ] Test backfill process on staging
- [ ] Test rollback procedures on staging
- [ ] Create database backup
- [ ] Run migration on production (off-peak)
- [ ] Verify migration with integrity checks
- [ ] Deploy v1.1 code (or use feature flags)
- [ ] Monitor performance for 24-48 hours
- [ ] Run backfill on production (if approved)
- [ ] Document completion in changelog

---

## References

- **[DEPRECATION_POLICY.md](./DEPRECATION_POLICY.md)** — API stability and versioning rules
- **[docs/change-log.md](./change-log.md)** — Version history documentation
- **[VAST DataBase Docs](./vast-integration.md)** — Database schema and API details

---

**Last Updated**: February 6, 2026
**Version**: 1.0
