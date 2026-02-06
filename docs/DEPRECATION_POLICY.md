# Deprecation Policy

## Overview

This document outlines the API stability commitment and deprecation procedures for exr-inspector across all versions.

---

## API Stability Commitment

### No Breaking Changes in v0.9.x and v1.x

exr-inspector guarantees **backward compatibility** across all patch and minor versions:

- **v0.9.0 through v0.9.x**: No breaking changes to the JSON output schema, function signatures, or configuration interface
- **v1.0.0 through v1.x**: No breaking changes to the JSON output schema, function signatures, or configuration interface
- **Breaking changes** (removals, signature changes, schema incompatibilities) **only occur in major version releases** (v2.0, v3.0, etc.)

### Major Version Requirement for Breaking Changes

To modify the API in incompatible ways, a new major version must be released:

- Major version increments (e.g., v1.0 → v2.0) are reserved for breaking changes
- Major versions may introduce incompatible schema changes, function signature changes, or configuration format changes
- Users must be given explicit notification and migration guidance before a major version is released

---

## Two-Release Notice for Removals

Any feature, field, or capability that will be removed must follow the **two-release deprecation window**:

1. **Deprecation Announcement** (Release N):
   - Feature is marked as deprecated in code (decorator/comments)
   - Deprecation warning is logged when feature is used
   - Changelog documents the deprecation with clear rationale
   - Documentation updated to recommend alternatives
   - Timeline provided: "Removal in v1.1" or "Removal in v2.0"

2. **Grace Period** (Release N+1):
   - Feature continues to work without change
   - Deprecation warnings continue
   - Users have time to migrate code/configurations

3. **Removal** (Release N+2):
   - Feature is removed
   - Removal is documented in changelog
   - No support provided for old code paths

### Example Deprecation Timeline

```
v0.9.0 (February 2026): Introduce feature X
v1.0.0 (Q2 2026): Mark feature X as deprecated
         - Reason: Better alternative Y available
         - Action required: Migrate to feature Y
         - Removal target: v1.1

v1.1.0 (Q3 2026): Feature X removed
         - Changelog documents removal
         - Migration guide references old docs
```

---

## JSON Output Schema Stability Guarantee

### Schema Versioning

The JSON output schema includes a `schema_version` field:

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

### Schema Evolution Rules

**v0.9.x and v1.x (schema_version: 1)**:
- Existing fields are **never removed**
- Existing fields are **never renamed**
- Existing fields are **never type-changed**
- New fields may be added (additions are backward compatible)
- New fields default to `null` or empty if not applicable

**Schema Version Increments** (v2.0+):
- New schema_version value (e.g., 2, 3) indicates breaking changes
- Old schema_version values may be deprecated but must be documented
- Explicit migration strategy provided

### Backward Compatible Changes (v0.9.x and v1.x)

**These changes do NOT increment schema_version**:

```json
// Adding a new optional field
{
  "schema_version": 1,
  "file": { ... },
  "parts": [ ... ],
  "channels": [ ... ],
  "new_field": null   // OK: optional, backward compatible
}

// Adding a new optional object
{
  "schema_version": 1,
  "file": { ... },
  "parts": [ ... ],
  "performance_metadata": {   // OK: new section, won't break parsers
    "extraction_time_ms": 125
  }
}

// Making a field more specific (but compatible)
{
  "schema_version": 1,
  "file": {
    "path": "string",
    "size_bytes": 1024,
    "mtime": "2026-02-06T10:00:00Z",
    "ctime": "2026-02-06T10:00:00Z"   // OK: new field, won't break parsers
  }
}
```

### Examples of Breaking Changes (major version only)

These require schema_version increment:

```json
// Removing a field (v2.0+)
// v1.x had "attributes" field, v2.0 removes it

// Renaming a field (v2.0+)
// v1.x had "compression", v2.0 renames to "compression_type"

// Changing field type (v2.0+)
// v1.x had "tile_width": 256 (int)
// v2.0 changes to "tile_width": "256x256" (string)

// Changing array element structure (v2.0+)
// v1.x had channels: [{"name": "R", "type": "FLOAT"}]
// v2.0 changes to channels: {"R": "FLOAT"} (object, not array)
```

---

## VAST Schema Versioning Approach

### Database Schema Evolution

The VAST DataBase schema includes built-in versioning to support future changes:

#### Current Schema (v1)

Four normalized tables:

| Table | Purpose | Status |
|-------|---------|--------|
| `files` | Root file records with path, size, mtime, embeddings | Stable (v0.9.0+) |
| `parts` | Multipart EXR structures | Stable (v0.9.0+) |
| `channels` | Channel definitions | Stable (v0.9.0+) |
| `attributes` | Custom EXR attributes | Stable (v0.9.0+) |

#### Schema Versioning Columns

Each table includes:

```python
schema_version: int         # Which schema version (1, 2, 3, ...)
created_at: timestamp       # When record was inserted
updated_at: timestamp       # When record was last modified
metadata: json              # Reserved for future use
```

This enables:
- Gradual migration between schema versions
- Coexistence of multiple schema versions
- Rollback procedures
- Migration scripts

#### Future Evolution (v1.1+)

When pixel statistics are added:

```python
# New table added (v2 schema)
CREATE TABLE pixel_stats (
    stat_id INT PRIMARY KEY,
    file_id INT REFERENCES files(file_id),
    part_index INT,
    channel_name STRING,
    stat_type ENUM('min', 'max', 'mean', 'stddev', 'nan_count', 'inf_count'),
    stat_value FLOAT,
    sampling_rate FLOAT,
    schema_version INT DEFAULT 1,  # Schema version field
    created_at TIMESTAMP,
    updated_at TIMESTAMP
)
```

**Backward Compatibility Approach**:
1. Old schema_version=1 records remain unchanged
2. New stat records use schema_version=2
3. Queries can filter by schema_version if needed
4. Migration window provided (see SCHEMA_MIGRATION_STRATEGY.md)

---

## Communicating Deprecations

### Changelog Format

Deprecations are documented in `docs/change-log.md`:

```markdown
## [v1.0.0] - 2026-Q2

### Deprecated
- **Feature**: Simple attribute filtering in validation_rules
  - **Reason**: Regex-based filtering is more flexible
  - **Replacement**: Use `validation_rules.attribute_patterns`
  - **Timeline**: Removal in v1.1 (Q3 2026)
  - **Migration**: See SCHEMA_MIGRATION_STRATEGY.md

### Added
- Regex-based attribute filtering in validation_rules
- Performance improvements (15% faster embedding computation)

### Fixed
- Handle empty channel lists without crashing
```

### Code Deprecation Markers

```python
import warnings

def old_extraction_method(path: str) -> dict:
    """Extract EXR metadata (DEPRECATED in v1.0.0).

    .. deprecated:: 1.0.0
        Use :func:`new_extraction_method` instead.
    """
    warnings.warn(
        "old_extraction_method is deprecated and will be removed in v1.1. "
        "Use new_extraction_method instead.",
        DeprecationWarning,
        stacklevel=2
    )
    # ... implementation ...
```

### Documentation Markers

```markdown
> ⚠️ **Deprecated**: This feature is deprecated as of v1.0.0 and will be
> removed in v1.1. Use [alternative feature](link) instead.
```

---

## Examples: Breaking vs Non-Breaking Changes

### Example 1: Adding Pixel Statistics (v1.1)

**Non-Breaking** (could be added in v0.9.x):

```python
# Before (v0.9.0)
{
  "schema_version": 1,
  "file": {...},
  "parts": [...],
  "channels": [...]
}

# After (v0.9.x or v1.x)
{
  "schema_version": 1,
  "file": {...},
  "parts": [...],
  "channels": [...],
  "stats": {          # ✅ New optional field, backward compatible
    "enabled": false,
    "sampling_rate": null
  }
}
```

**Breaking Change Approach** (requires v2.0):

```python
# Removing optional fields from channels array (requires major version)
# Before: channels[i] = {"name": "R", "type": "FLOAT", "x_sampling": 1}
# After: channels[i] = {"name": "R", "type": "FLOAT"}  # BREAKING!
# Requires: schema_version: 2
```

### Example 2: Changing Attribute Representation

**Non-Breaking** (backward compatible):

```python
# Before (v0.9.0)
{
  "attributes": {
    "comments": "string value",
    "author": "string value"
  }
}

# After (v0.9.x or v1.x) - Add type information
{
  "attributes": {
    "comments": "string value",
    "author": "string value"
  },
  "attributes_with_types": {  # ✅ New field, old field still present
    "comments": {"type": "STRING", "value": "string value"},
    "author": {"type": "STRING", "value": "string value"}
  }
}
```

**Breaking Change** (requires v2.0):

```python
# Removing old format and keeping only typed version (BREAKING!)
{
  "attributes": {
    "comments": {"type": "STRING", "value": "string value"},
    "author": {"type": "STRING", "value": "string value"}
  }
  # Old "attributes" format is gone - requires schema_version: 2
}
```

### Example 3: Configuration Format Evolution

**Non-Breaking** (backward compatible):

```python
# Before (v0.9.0)
config = {
  "enable_meta": True,
  "enable_stats": False
}

# After (v0.9.x or v1.x) - Support both formats
config_v1 = {
  "enable_meta": True,
  "enable_stats": False
}

config_v2 = {
  "features": {
    "metadata": {"enabled": True},
    "statistics": {"enabled": False}
  }
}

def parse_config(config):
    # Support both formats - backward compatible
    if "features" in config:
        return config  # New format
    else:
        return convert_legacy_format(config)  # Old format still works
```

**Breaking Change** (requires v2.0):

```python
# Remove old format support entirely (BREAKING!)
def parse_config(config):
    # Only new format supported in v2.0
    if "features" not in config:
        raise ValueError("Config must use v2.0 format")
    return config
```

---

## Support Policy

### During Release Candidate (v0.9.x)

- Active development and bug fixes
- Community feedback incorporated
- API may be adjusted based on feedback
- Schema may be refined
- Documented in release notes if changes occur

### After v1.0.0

- Strict API stability commitment enforced
- Bug fixes and security patches only
- Feature development deferred to v1.1+
- Breaking changes only in v2.0+

### End of Life (EOL)

- No specific EOL policy yet
- Plan to support v0.9.x and v1.x concurrently during transition
- EOL dates will be announced with 6 months notice

---

## Questions & Clarifications

**Q: Why no breaking changes in v0.9.x?**
A: To signal production-readiness and ensure enterprise users can safely adopt without fear of upgrade churn.

**Q: What if a critical security issue requires API changes?**
A: Security fixes take precedence. A critical patch (e.g., v1.0.5) may include necessary changes with full documentation and migration guidance.

**Q: Can we fast-track to v2.0 if major restructuring is needed?**
A: Unlikely within the first year. The API surface is small and the core architecture is solid. Major changes would only occur if the project's scope fundamentally shifts.

**Q: How does this affect the VAST DataBase schema?**
A: See "VAST Schema Versioning Approach" section above. Database schema evolution is independent of the semantic version number.

---

## References

- **[SCHEMA_MIGRATION_STRATEGY.md](./SCHEMA_MIGRATION_STRATEGY.md)** — How to migrate data between schema versions
- **[docs/change-log.md](./change-log.md)** — Version history and change documentation
- **[README.md](../README.md)** — Known limitations and feature status
- **Semantic Versioning**: https://semver.org/

---

**Last Updated**: February 6, 2026
**Version**: 1.0
