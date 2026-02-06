# Schema Evolution and Migration Strategy

## Overview

This document describes how the exr-inspector VAST Database schema evolves over time, manages versions, and enables safe migrations without data loss.

**Current Version**: v1.0.0
**Target Version Path**: v1.0.0 → v1.1.0 → v2.0.0

---

## Current Schema Version (v1.0.0)

### Tables

| Table | Purpose | Key Fields |
|-------|---------|-----------|
| **files** | Master record per EXR | file_id, file_path, metadata_embedding |
| **parts** | Subimages within files | file_id, part_index, compression, is_deep |
| **channels** | Individual channels | file_id, channel_name, channel_fingerprint |
| **attributes** | Custom metadata | file_id, attr_name, value_json |
| **stats** | Pixel statistics | file_id, min/max/mean values (prepared) |
| **validation_results** | Policy violations | file_id, severity, rule_id |

### Schema Fields

See `/vast_schemas.py` for complete field definitions.

**Key versioning fields**:
- `schema_version`: "1.0.0" (stored in files table)
- `inspector_version`: e.g., "1.2.3" (tool version that inspected the file)

### Vector Dimensions (v1.0.0)

- **metadata_embedding**: 384D (cosine distance)
- **channel_fingerprint**: 128D (euclidean distance)

---

## Future Fields and Schema Evolution Path

### v1.1.0 (Minor Enhancement - Backward Compatible)

**Goal**: Add optional fields for better analytics without breaking existing code.

#### New Fields in files Table

```python
pa.field("show_name", pa.string(), nullable=True, metadata={
    "description": "Show/project extracted from path",
    "example": "PRJX001",
    "source": "path parsing"
}),
pa.field("shot_name", pa.string(), nullable=True, metadata={
    "description": "Shot identifier extracted from path",
    "example": "SH_0010",
    "source": "path parsing"
}),
pa.field("sequence_name", pa.string(), nullable=True, metadata={
    "description": "Sequence identifier extracted from path",
    "example": "SEQ_010",
    "source": "path parsing"
}),
pa.field("frame_number", pa.int32(), nullable=True, metadata={
    "description": "Frame number extracted from filename",
    "example": 1,
    "source": "path parsing"
}),
pa.field("colorspace", pa.string(), nullable=True, metadata={
    "description": "Color space from custom attributes",
    "example": "linear",
    "source": "attributes.colorspace"
}),
```

#### New Fields in parts Table

```python
pa.field("color_space", pa.string(), nullable=True, metadata={
    "description": "Color space metadata from part attributes",
    "example": "linear"
}),
pa.field("chromaticities", pa.string(), nullable=True, metadata={
    "description": "Chromaticity info as JSON",
    "example": '{"red": [0.64, 0.33], ...}',
    "format": "json"
}),
```

#### New Fields in channels Table

```python
pa.field("bit_depth", pa.int32(), nullable=True, metadata={
    "description": "Bit depth (16 for HALF, 32 for FLOAT)",
    "example": 32
}),
```

#### Migration Path (v1.0.0 → v1.1.0)

1. **Add nullable columns** to existing tables:
   ```sql
   ALTER TABLE files ADD COLUMN show_name VARCHAR NULL;
   ALTER TABLE files ADD COLUMN shot_name VARCHAR NULL;
   ALTER TABLE files ADD COLUMN sequence_name VARCHAR NULL;
   ALTER TABLE files ADD COLUMN frame_number INT NULL;
   ALTER TABLE files ADD COLUMN colorspace VARCHAR NULL;
   ```

2. **Backfill with path parsing** (gradual):
   ```python
   import re
   from vast_db_persistence import Session

   session = Session(...)
   files_table = session.table("exr_metadata.files")

   # Query all files
   files = files_table.select("SELECT file_id, file_path FROM files")

   for file_row in files:
       # Parse path
       show = _extract_show_from_path(file_row['file_path'])
       shot = _extract_shot_from_path(file_row['file_path'])

       # Update
       files_table.update(
           values={"show_name": show, "shot_name": shot},
           where=f"file_id = '{file_row['file_id']}'"
       )
   ```

3. **Update inspector code** to populate new fields:
   ```python
   def payload_to_files_row(payload, metadata_embedding, file_id=None):
       # ... existing code ...

       # v1.1.0: Add path parsing
       file_path = payload["file"]["path"]
       show_name = _extract_show_from_path(file_path)
       shot_name = _extract_shot_from_path(file_path)

       # Include in data dict
       data["show_name"] = [show_name]
       data["shot_name"] = [shot_name]
   ```

4. **No schema version bump needed** (backward compatible)

### v2.0.0 (Major Revision - Breaking Changes)

**Goal**: Restructure for better analytics support (requires data migration).

#### Major Changes

1. **Rename embedding dimensions**:
   ```
   metadata_embedding → semantic_embedding (stays 384D)
   channel_fingerprint → structure_fingerprint (stays 128D)
   ```

2. **Introduce new vector type**:
   ```python
   pa.field("path_embedding", pa.list_(pa.float32()), nullable=True, metadata={
       "description": "File path semantic embedding (256D)",
       "dimension": "256",
       "purpose": "Cluster renders by naming patterns"
   }),
   ```

3. **Separate path parsing into attributes**:
   ```python
   # Instead of show_name, shot_name fields in files,
   # use extracted_metadata JSONB:
   pa.field("extracted_metadata", pa.string(), nullable=True, metadata={
       "description": "Parsed show/shot/frame as JSON",
       "example": '{"show": "PRJX001", "shot": "SH_0010", "frame": 1}',
       "format": "json"
   }),
   ```

#### Migration Path (v1.0.0/v1.1.0 → v2.0.0)

**Phase 1: Parallel Systems (Week 1-2)**
```python
# Keep v1.x tables, create v2.0.0 tables alongside
CREATE SCHEMA exr_metadata_v2;
CREATE TABLE exr_metadata_v2.files AS SELECT * FROM exr_metadata.files;
# ... add new columns, rename existing ones ...
```

**Phase 2: Gradual Migration (Week 3-4)**
```python
# Dual-write: new records go to both v1 and v2
def handler(ctx, event):
    payload = inspect_exr(event['data']['path'])

    # Write to v1 (legacy)
    persist_to_vast_database(payload, event, schema="exr_metadata")

    # Write to v2 (new)
    persist_to_vast_database_v2(payload, event, schema="exr_metadata_v2")
```

**Phase 3: Read Migration (Week 5)**
```python
# Update analytics queries to read from v2
# Keep v1 for fallback
def query_files(schema="exr_metadata_v2"):
    try:
        return query_v2_schema(schema)
    except:
        return query_v1_schema("exr_metadata")  # Fallback
```

**Phase 4: Cleanup (Week 6+)**
```sql
-- Drop v1 tables after no references
DROP TABLE exr_metadata.files CASCADE;
DROP SCHEMA exr_metadata;

-- Rename v2 to canonical name
ALTER SCHEMA exr_metadata_v2 RENAME TO exr_metadata;
```

---

## Strategy: Pre-Create Columns vs JSONB Fallback

### Pre-Create Approach (Current: v1.0.0)

**Structure**: Explicit columns for all known fields

```python
# explicit_embedding.py
FILES_SCHEMA = pa.schema([
    pa.field("file_id", pa.string()),
    pa.field("metadata_embedding", pa.list_(pa.float32())),
    pa.field("channel_fingerprint", pa.list_(pa.float32())),
    # ... many explicit fields ...
])
```

**Advantages**:
- Type safety (database enforces types)
- Query performance (no JSON parsing)
- Clear schema documentation
- Easy to index individual fields

**Disadvantages**:
- Schema changes require ALTER TABLE
- Storage overhead for sparse fields
- Migration complexity for new fields

**When to use**:
- Stable, well-defined fields
- Frequent queries on those fields
- Performance-critical applications

### JSONB Fallback Approach (Optional: v2.0.0)

**Structure**: Store unstructured data in JSONB when column doesn't exist

```python
# hybrid_embedding.py
FILES_SCHEMA = pa.schema([
    pa.field("file_id", pa.string()),
    pa.field("metadata_embedding", pa.list_(pa.float32())),
    # ... standard fields ...

    # Future: store unknown attributes here
    pa.field("custom_attributes", pa.string(), nullable=True, metadata={
        "description": "Unstructured attributes as JSON",
        "format": "json"
    }),
])
```

**Example Usage**:
```python
# For unknown custom attributes
payload["attributes"]["custom"] = {
    "workflow": "maya_to_arnold",
    "custom_param": 42,
}

# Store in JSONB column
custom_attrs = json.dumps(payload["attributes"]["custom"])
```

**Advantages**:
- Flexible for unknown data
- No schema changes needed
- Can add fields without migration
- Good for versioned data

**Disadvantages**:
- Slower queries (JSON parsing)
- No type safety
- Hard to index
- Query optimization difficult

**When to use**:
- Rapidly evolving data
- Custom user attributes
- Optional experimental fields
- Fallback for unexpected data

---

## Backfill Scripts Pattern

### Template: Path Parsing Backfill

```python
"""
Backfill show_name, shot_name from file paths.
Useful for v1.0.0 → v1.1.0 migration.
"""

import re
from typing import Optional
from vastdb_sdk import Session

def extract_show(path: str) -> Optional[str]:
    """Extract show identifier from path."""
    # Pattern: /renders/PRJX###/...
    match = re.search(r'/renders/([A-Z]{3}[0-9]{3})', path)
    return match.group(1) if match else None

def extract_shot(path: str) -> Optional[str]:
    """Extract shot identifier from path."""
    # Pattern: .../SH_####/...
    match = re.search(r'/(SH_[0-9]{4})', path)
    return match.group(1) if match else None

def backfill_path_metadata(
    session: Session,
    schema_name: str = "exr_metadata",
    batch_size: int = 100,
    dry_run: bool = False,
):
    """Backfill show/shot metadata from paths."""
    files_table = session.table(f"{schema_name}.files")

    # Query all files
    all_files = files_table.select("SELECT file_id, file_path FROM files")
    total = len(all_files)

    print(f"Backfilling {total} files...")

    processed = 0
    for i in range(0, total, batch_size):
        batch = all_files[i : i + batch_size]
        updates = []

        for file_row in batch:
            path = file_row["file_path"]
            show = extract_show(path)
            shot = extract_shot(path)

            if show or shot:
                updates.append({
                    "file_id": file_row["file_id"],
                    "show_name": show,
                    "shot_name": shot,
                })

        # Perform batch update
        if not dry_run:
            for update in updates:
                files_table.update(
                    values={
                        "show_name": update["show_name"],
                        "shot_name": update["shot_name"],
                    },
                    where=f"file_id = '{update['file_id']}'"
                )

        processed += len(batch)
        print(f"  Processed {processed}/{total} files...")

    print(f"Backfill complete!")

if __name__ == "__main__":
    from vastdb_sdk import Session

    session = Session(
        endpoint="https://vast.example.com",
        access_key="...",
        secret_key="...",
    )

    backfill_path_metadata(session, dry_run=False)
```

### Template: Vectorization Backfill

```python
"""
Recompute embeddings with new algorithm.
Useful when embedding logic changes.
"""

import json
from vast_db_persistence import compute_metadata_embedding, Session

def backfill_embeddings(
    session: Session,
    schema_name: str = "exr_metadata",
    batch_size: int = 50,
):
    """Recompute metadata embeddings for all files."""
    files_table = session.table(f"{schema_name}.files")

    # Query all files with raw_output
    all_files = files_table.select(
        "SELECT file_id, raw_output FROM files"
    )

    for i, file_row in enumerate(all_files):
        # Deserialize raw JSON
        raw_output = json.loads(file_row["raw_output"])

        # Recompute embedding with NEW algorithm
        new_embedding = compute_metadata_embedding(raw_output)

        # Update record
        files_table.update(
            values={"metadata_embedding": new_embedding},
            where=f"file_id = '{file_row['file_id']}'"
        )

        if (i + 1) % batch_size == 0:
            print(f"Updated {i + 1}/{len(all_files)} files")

    print(f"Embedding backfill complete!")
```

### Verification Script

```python
"""Verify backfill correctness."""

def verify_backfill(
    session: Session,
    schema_name: str = "exr_metadata",
    sample_size: int = 100,
):
    """Spot-check backfill results."""
    files_table = session.table(f"{schema_name}.files")

    # Random sample
    sample = files_table.select(
        f"SELECT file_id, show_name, shot_name, raw_output "
        f"FROM files ORDER BY RANDOM() LIMIT {sample_size}"
    )

    errors = []
    for file_row in sample:
        show = file_row["show_name"]
        shot = file_row["shot_name"]
        raw = json.loads(file_row["raw_output"])
        path = raw["file"]["path"]

        expected_show = extract_show(path)
        expected_shot = extract_shot(path)

        if show != expected_show:
            errors.append(
                f"File {file_row['file_id']}: "
                f"expected show={expected_show}, got {show}"
            )

        if shot != expected_shot:
            errors.append(
                f"File {file_row['file_id']}: "
                f"expected shot={expected_shot}, got {shot}"
            )

    if errors:
        print(f"Verification FAILED ({len(errors)} errors):")
        for err in errors[:10]:
            print(f"  - {err}")
        return False
    else:
        print(f"Verification PASSED ({sample_size} samples checked)")
        return True
```

---

## Rollback Procedures

### Rollback Before Completion

If migration fails mid-way, rollback to previous schema:

```python
def rollback_migration(
    session: Session,
    from_schema: str = "exr_metadata_v2",
    to_schema: str = "exr_metadata",
):
    """Rollback to previous schema version."""
    print(f"Rolling back from {from_schema} to {to_schema}")

    # 1. Stop writes to new schema
    # (update handler to write only to old schema)

    # 2. Verify old schema still has data
    old_count = session.table(f"{to_schema}.files").select(
        f"SELECT COUNT(*) as count FROM files"
    )[0]["count"]
    print(f"  Old schema has {old_count} files")

    # 3. Drop new schema
    try:
        session.execute(f"DROP SCHEMA IF EXISTS {from_schema} CASCADE")
        print(f"  Dropped {from_schema}")
    except Exception as e:
        print(f"  Warning: Could not drop {from_schema}: {e}")

    # 4. Revert to old schema in code
    print(f"  Update handler to use {to_schema}")
    print(f"Rollback complete!")
```

### Rollback After Completion

If data corruption discovered post-migration:

```python
def restore_from_backup(
    backup_path: str,
    session: Session,
    schema_name: str = "exr_metadata",
):
    """Restore database from backup."""
    print(f"Restoring from backup: {backup_path}")

    # 1. Create temporary schema
    temp_schema = f"{schema_name}_restore"
    session.execute(f"DROP SCHEMA IF EXISTS {temp_schema} CASCADE")

    # 2. Restore from backup to temp
    with open(backup_path, 'r') as f:
        restore_sql = f.read()
    session.execute(restore_sql)
    print(f"  Restored to {temp_schema}")

    # 3. Rename schemas
    session.execute(f"ALTER SCHEMA {schema_name} RENAME TO {schema_name}_broken")
    session.execute(f"ALTER SCHEMA {temp_schema} RENAME TO {schema_name}")
    print(f"  Swapped schemas")

    # 4. Keep broken schema for forensics
    print(f"Restore complete! Broken data preserved in {schema_name}_broken")
```

### Test Rollback

```bash
# Before doing production migration, test rollback:

# 1. Create test environment with copy of production data
# 2. Run migration in test
# 3. Verify data integrity
# 4. Trigger rollback
# 5. Confirm rollback works correctly

# Then proceed with production migration
```

---

## Version Compatibility Query

### Version-Aware Queries

```python
def query_with_version_awareness(
    session: Session,
    query_v1: str,
    query_v2: str,
):
    """Execute version-appropriate query."""
    # Check schema version
    try:
        version_result = session.execute(
            "SELECT schema_version FROM exr_metadata.files LIMIT 1"
        )
        version = version_result[0]["schema_version"]
    except:
        version = "1.0.0"  # Assume v1 if not found

    if version.startswith("1."):
        return session.execute(query_v1)
    elif version.startswith("2."):
        return session.execute(query_v2)
    else:
        raise ValueError(f"Unknown schema version: {version}")
```

### Queries That Work Across Versions

When possible, write queries that work with both v1 and v2:

```sql
-- Version-agnostic: use available columns
SELECT
    f.file_id,
    f.file_path,
    -- These columns exist in both v1.0.0 and v1.1.0
    f.size_bytes,
    f.multipart_count,
    f.is_deep,
    -- Optional: use COALESCE for v1.1.0 fields
    COALESCE(f.show_name, 'UNKNOWN') as show_name,
    -- Count channels (works in all versions)
    (SELECT COUNT(*) FROM channels c WHERE c.file_id = f.file_id) as channel_count
FROM files f
WHERE f.last_inspected >= DATE('now', '-7 days')
ORDER BY f.last_inspected DESC
LIMIT 100;
```

---

## See Also

- [VECTOR_STRATEGY.md](VECTOR_STRATEGY.md) - Embedding computation (may change in v2.0.0)
- [VAST_ANALYTICS_QUERIES.md](VAST_ANALYTICS_QUERIES.md) - Query examples (version-aware)
- [TROUBLESHOOTING.md](TROUBLESHOOTING.md) - Migration troubleshooting
