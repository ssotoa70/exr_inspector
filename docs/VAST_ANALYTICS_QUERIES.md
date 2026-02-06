# VAST Analytics Queries for VFX Pipelines

## Overview

This document provides production-ready SQL queries for analyzing EXR metadata stored in VAST Database. These queries enable VFX pipeline teams to understand render characteristics, detect anomalies, track inventory, and enforce quality standards.

**Database Schema**: `exr_metadata` (files, parts, channels, attributes, validation_results tables)

---

## Query 1: Find Renders Similar to a Reference (Metadata)

**Use Case**: When you want to find all renders that have similar characteristics to a reference file (same render engine, resolution, channel setup).

**Example Scenario**: You have a "golden render" from a successful shot and want to find all other renders with the same metadata pattern.

```sql
-- Find renders with metadata similarity < 0.3 (higher is more different)
-- This assumes you've computed the reference embedding in your application
SELECT
    f.file_id,
    f.file_path,
    f.size_bytes,
    f.multipart_count,
    f.is_deep,
    f.is_tiled,
    DISTANCE(f.metadata_embedding, ?, 'cosine') as metadata_distance,
    f.inspection_count,
    f.last_inspected
FROM files f
WHERE DISTANCE(f.metadata_embedding, ?, 'cosine') < 0.3
  AND f.file_path_normalized != ?  -- Exclude reference itself
ORDER BY metadata_distance ASC
LIMIT 50
```

**Parameters**:
1. Query vector (computed via `compute_metadata_embedding()`)
2. Query vector (same as #1)
3. Normalized path of reference file

**Expected Results**:
- file_id: Unique identifier
- file_path: Full path to render
- size_bytes: File size for cost analysis
- multipart_count: Number of parts (1 = single-part, >1 = multipart)
- metadata_distance: 0 = identical, higher = more different

**Example Output**:
```
file_id          | file_path                                  | size_bytes | multipart_count | metadata_distance
-----------------|-----------------------------------------------|------------|-----------------|------------------
abc123...        | /renders/shot_001/beauty_v001.exr          | 104857600  | 1               | 0.0234
abc124...        | /renders/shot_001/beauty_v002.exr          | 104857600  | 1               | 0.0251
abc125...        | /renders/shot_002/beauty_v001.exr          | 104857600  | 1               | 0.0892
```

---

## Query 2: Find Files with Specific Channel Composition

**Use Case**: Find all renders matching a specific channel layout (e.g., all RGBA 32-bit float files).

**Example Scenario**: You need to gather all beauty passes for re-grading.

```sql
-- Find all files that have exactly RGBA channels as float
SELECT
    f.file_id,
    f.file_path,
    f.size_bytes,
    COUNT(c.channel_id) as total_channels,
    GROUP_CONCAT(DISTINCT c.layer_name) as layers,
    GROUP_CONCAT(c.channel_name ORDER BY c.channel_name) as channel_list,
    f.last_inspected
FROM files f
JOIN channels c ON f.file_id = c.file_id
WHERE c.channel_type = 'FLOAT'
  AND c.channel_name IN ('R', 'G', 'B', 'A')
GROUP BY f.file_id
HAVING COUNT(c.channel_id) = 4  -- Exactly 4 channels
ORDER BY f.last_inspected DESC
LIMIT 100
```

**Expected Results**:
```
file_id    | file_path                    | size_bytes | total_channels | layers | channel_list
------------|------------------------------|------------|----------------|--------|------------------
file001    | /renders/shot_001/beauty.exr | 104857600  | 4              | NULL   | A, B, G, R
file002    | /renders/shot_002/beauty.exr | 104857600  | 4              | NULL   | A, B, G, R
```

### Variant: Find Multi-Layer Renders

```sql
-- Find all files with multiple layers (beauty, diffuse, etc.)
SELECT
    f.file_id,
    f.file_path,
    COUNT(DISTINCT c.layer_name) as unique_layers,
    GROUP_CONCAT(DISTINCT c.layer_name) as layer_names,
    COUNT(c.channel_id) as total_channels,
    f.multipart_count
FROM files f
JOIN channels c ON f.file_id = c.file_id
WHERE c.layer_name IS NOT NULL
GROUP BY f.file_id
HAVING COUNT(DISTINCT c.layer_name) > 1
ORDER BY unique_layers DESC, f.last_inspected DESC
LIMIT 50
```

---

## Query 3: Detect Anomalies (Unusual Metadata Patterns)

**Use Case**: Find renders that deviate significantly from normal patterns (unusual compression, incorrect bit depth, unexpected channel counts).

**Example Scenario**: Quality control wants to identify renders that don't match pipeline standards.

```sql
-- Find renders with anomalous characteristics
-- (high file size, unexpected compression, deep EXR files when not expected)
SELECT
    f.file_id,
    f.file_path,
    f.size_bytes,
    f.size_bytes / 1024.0 / 1024.0 as size_mb,
    p.compression,
    f.is_deep,
    f.is_tiled,
    COUNT(DISTINCT c.channel_id) as channel_count,
    CASE
        WHEN f.size_bytes > 500 * 1024 * 1024 THEN 'LARGE_FILE'
        WHEN f.is_deep THEN 'DEEP_EXR'
        WHEN p.compression = 'NONE' THEN 'UNCOMPRESSED'
        WHEN COUNT(DISTINCT c.channel_id) > 50 THEN 'MANY_CHANNELS'
        ELSE 'NORMAL'
    END as anomaly_type,
    f.inspection_count,
    f.last_inspected
FROM files f
LEFT JOIN parts p ON f.file_id = p.file_id
LEFT JOIN channels c ON f.file_id = c.file_id
WHERE
    (f.size_bytes > 500 * 1024 * 1024)
    OR (f.is_deep = true)
    OR (p.compression = 'NONE')
    OR (COUNT(DISTINCT c.channel_id) > 50)
GROUP BY f.file_id
ORDER BY f.size_bytes DESC, f.last_inspected DESC
LIMIT 100
```

**Explanation**:
- **LARGE_FILE**: >500 MB (storage/bandwidth concern)
- **DEEP_EXR**: Contains deep data (expensive to render and store)
- **UNCOMPRESSED**: No compression (storage inefficiency)
- **MANY_CHANNELS**: >50 channels (unusual, may indicate pipeline error)

**Expected Output**:
```
file_id | file_path | size_mb | anomaly_type      | channel_count | last_inspected
--------|-----------|---------|-------------------|---------------|------------------
f123    | shot_001/render.exr | 612.5 | LARGE_FILE | 8 | 2025-02-05T10:30:00Z
f124    | shot_002/render.exr | 256.0 | DEEP_EXR   | 4 | 2025-02-05T09:15:00Z
```

---

## Query 4: Inventory Deep EXRs by Render Engine

**Use Case**: Understand which render engines produce deep EXRs, for capacity planning and cost analysis.

**Example Scenario**: Pipeline lead wants to know storage impact of deep renders by render engine.

```sql
-- Inventory deep EXRs by suspected render engine
-- (inferred from channel patterns and metadata)
SELECT
    CASE
        WHEN GROUP_CONCAT(c.channel_name) LIKE '%Z%' AND f.is_deep THEN 'Arnold (Deep Z)'
        WHEN f.is_deep AND COUNT(DISTINCT c.layer_name) > 3 THEN 'VRay (Deep Multi-Layer)'
        WHEN f.is_deep AND f.is_tiled THEN 'RenderMan (Tiled Deep)'
        WHEN f.is_deep THEN 'Generic Deep'
        ELSE 'Non-Deep'
    END as render_engine_inferred,
    COUNT(f.file_id) as file_count,
    SUM(f.size_bytes) / 1024.0 / 1024.0 / 1024.0 as total_size_gb,
    AVG(f.size_bytes) / 1024.0 / 1024.0 as avg_size_mb,
    SUM(f.size_bytes) / COUNT(f.file_id) / 1024.0 / 1024.0 as mean_size_mb,
    MIN(f.last_inspected) as earliest_file,
    MAX(f.last_inspected) as latest_file
FROM files f
LEFT JOIN channels c ON f.file_id = c.file_id
WHERE f.is_deep = true
GROUP BY render_engine_inferred
ORDER BY total_size_gb DESC
```

**Expected Output**:
```
render_engine_inferred | file_count | total_size_gb | avg_size_mb | earliest_file | latest_file
-----------------------|------------|---------------|-------------|---------------|------------------
Arnold (Deep Z)        | 245        | 125.4         | 524.5       | 2025-01-15    | 2025-02-05
RenderMan (Tiled Deep) | 89         | 67.2          | 756.8       | 2025-01-20    | 2025-02-04
VRay (Deep Multi-Layer)| 34         | 28.1          | 847.3       | 2025-02-01    | 2025-02-05
```

---

## Query 5: Validation Failures by Policy

**Use Case**: Track which renders are failing validation checks and what the policy violations are.

**Example Scenario**: Studio wants to understand which shots need re-renders to meet delivery standards.

```sql
-- Find validation failures grouped by policy and severity
SELECT
    vr.policy_id,
    vr.policy_version,
    vr.rule_id,
    vr.severity,
    COUNT(vr.validation_id) as failure_count,
    COUNT(DISTINCT vr.file_id) as unique_files_affected,
    GROUP_CONCAT(DISTINCT f.file_path LIMIT 3) as example_files,
    vr.message as violation_description,
    vr.suggested_fix
FROM validation_results vr
JOIN files f ON vr.file_id = f.file_id
WHERE vr.severity IN ('WARN', 'FAIL')
GROUP BY vr.policy_id, vr.rule_id
ORDER BY failure_count DESC
LIMIT 50
```

**Expected Output**:
```
policy_id | severity | rule_id | failure_count | unique_files | message
-----------|----------|---------|---------------|--------------|------------------
vfx_v2    | FAIL     | compression_check | 42 | 42 | Compression type NONE detected
vfx_v2    | WARN     | deep_data_check   | 28 | 28 | Unexpected deep data in beauty pass
vfx_v2    | WARN     | channel_bitdepth  | 156| 145| Float16 detected, float32 expected
```

### Variant: Validation Summary by Shot

```sql
-- Show validation status by shot/sequence
SELECT
    SUBSTR(f.file_path, 1, INSTR(f.file_path, '/') - 1) as project,
    SUBSTR(f.file_path, INSTR(f.file_path, '/') + 1) as shot_info,
    COUNT(DISTINCT f.file_id) as total_renders,
    COUNT(DISTINCT CASE WHEN vr.severity = 'FAIL' THEN vr.file_id END) as failed_renders,
    COUNT(DISTINCT CASE WHEN vr.severity = 'WARN' THEN vr.file_id END) as warned_renders,
    ROUND(100.0 * COUNT(DISTINCT CASE WHEN vr.severity IS NULL THEN vr.file_id END)
          / COUNT(DISTINCT f.file_id), 1) as percent_passing,
    MAX(f.last_inspected) as last_checked
FROM files f
LEFT JOIN validation_results vr ON f.file_id = vr.file_id
GROUP BY project, shot_info
ORDER BY percent_passing ASC, failed_renders DESC
```

---

## Query 6: Show/Shot/Frame Analytics

**Use Case**: Understand render patterns and quality by show, shot, and frame number.

**Example Scenario**: Editorial wants to understand which shots have been rendered and their quality status.

```sql
-- Extract show/shot/frame info from file paths
-- Assumes standard VFX path convention: /project/show/sequence/shot/type.frame.exr
SELECT
    REGEXP_SUBSTR(f.file_path, '([^/]+)/([^/]+)/([^/]+)/([^/]+)/', 1, 1, NULL, 1) as show,
    REGEXP_SUBSTR(f.file_path, '([^/]+)/([^/]+)/([^/]+)/([^/]+)/', 1, 1, NULL, 2) as sequence,
    REGEXP_SUBSTR(f.file_path, '([^/]+)/([^/]+)/([^/]+)/([^/]+)/', 1, 1, NULL, 3) as shot_num,
    REGEXP_SUBSTR(f.file_path, '([^/]+)/([^/]+)/([^/]+)/([^/]+)/', 1, 1, NULL, 4) as render_type,
    REGEXP_SUBSTR(f.file_path, '\.(\d+)\.exr', 1, 1, NULL, 1) as frame_number,
    COUNT(f.file_id) as render_count,
    COUNT(DISTINCT DATE(f.last_inspected)) as days_span,
    MAX(f.last_inspected) as latest_render,
    SUM(f.size_bytes) / 1024.0 / 1024.0 as total_size_mb
FROM files f
WHERE f.file_path LIKE '/renders/%'
GROUP BY show, sequence, shot_num, render_type
ORDER BY show, sequence, shot_num, render_type
```

**Note**: The exact regex patterns depend on your studio's naming conventions. Adjust `REGEXP_SUBSTR` patterns accordingly.

**Example Output**:
```
show    | sequence | shot_num | render_type | frame_count | latest_render | total_size_mb
--------|----------|----------|-------------|-------------|---------------|---------------
PRJX001 | SEQ_010  | SH_0010  | BEAUTY      | 120         | 2025-02-05    | 24576.5
PRJX001 | SEQ_010  | SH_0010  | DIFFUSE     | 120         | 2025-02-05    | 12288.3
PRJX001 | SEQ_010  | SH_0020  | BEAUTY      | 180         | 2025-02-04    | 36864.2
```

### Simplified Version (Path-Based)

```sql
-- Simpler approach: just analyze top-level directory structure
SELECT
    SUBSTR(f.file_path, 1, INSTR(SUBSTR(f.file_path, 2), '/')) as top_level_dir,
    COUNT(f.file_id) as file_count,
    SUM(f.size_bytes) / 1024.0 / 1024.0 / 1024.0 as total_gb,
    COUNT(CASE WHEN f.is_deep THEN 1 END) as deep_count,
    COUNT(CASE WHEN f.multipart_count > 1 THEN 1 END) as multipart_count,
    MIN(f.last_inspected) as earliest,
    MAX(f.last_inspected) as latest
FROM files f
GROUP BY top_level_dir
ORDER BY total_gb DESC
LIMIT 20
```

---

## Query 7: Compression Type Analysis

**Use Case**: Understand compression distribution and storage efficiency.

**Example Scenario**: Pipeline optimization - determine which compression methods are actually being used.

```sql
-- Analyze compression types across all renders
SELECT
    p.compression,
    COUNT(p.part_index) as part_count,
    COUNT(DISTINCT p.file_id) as unique_files,
    SUM(f.size_bytes) / 1024.0 / 1024.0 / 1024.0 as total_gb,
    AVG(f.size_bytes) / 1024.0 / 1024.0 as avg_file_mb,
    COUNT(CASE WHEN f.is_deep THEN 1 END) as deep_count,
    COUNT(CASE WHEN f.is_tiled THEN 1 END) as tiled_count,
    MAX(f.last_inspected) as latest_usage
FROM parts p
JOIN files f ON p.file_id = f.file_id
GROUP BY p.compression
ORDER BY total_gb DESC
```

**Expected Output**:
```
compression | part_count | unique_files | total_gb | avg_file_mb | deep_count | latest_usage
------------|------------|--------------|----------|-------------|------------|------------------
ZIP         | 1240       | 620          | 256.5    | 424.3       | 0          | 2025-02-05
PIZ         | 890        | 445          | 189.3    | 437.2       | 45         | 2025-02-05
DWAB        | 234        | 117          | 124.8    | 1064.5      | 0          | 2025-02-04
NONE        | 45         | 45           | 92.1     | 2048.9      | 0          | 2025-01-28
```

---

## Query 8: Render Performance Trending

**Use Case**: Track inspection frequency and file modification patterns over time.

**Example Scenario**: Identify which shots are being re-rendered most frequently.

```sql
-- Track render iterations by day
SELECT
    DATE(f.last_inspected) as inspection_date,
    COUNT(f.file_id) as new_files_found,
    SUM(f.inspection_count) as total_inspections_ever,
    AVG(f.inspection_count) as avg_iterations_per_file,
    SUM(f.size_bytes) / 1024.0 / 1024.0 / 1024.0 as daily_gb,
    COUNT(DISTINCT SUBSTR(f.file_path, 1, INSTR(f.file_path, '/') - 1)) as unique_shots
FROM files f
WHERE DATE(f.last_inspected) >= DATE('now', '-30 days')
GROUP BY DATE(f.last_inspected)
ORDER BY inspection_date DESC
```

**Expected Output**:
```
inspection_date | new_files | total_inspections | avg_iterations | daily_gb | unique_shots
-----------------|-----------|-------------------|-----------------|----------|---------------
2025-02-05       | 156       | 324               | 2.08            | 128.4    | 12
2025-02-04       | 142       | 298               | 2.10            | 121.2    | 11
2025-02-03       | 98        | 201               | 2.05            | 84.3     | 8
```

---

## Query 9: Inspection Coverage and Staleness

**Use Case**: Identify files that haven't been inspected recently (potential missing renders).

**Example Scenario**: Asset manager wants to know if all expected renders are present.

```sql
-- Find stale renders (not inspected in >7 days)
SELECT
    f.file_id,
    f.file_path,
    f.last_inspected,
    JULIANDAY('now') - JULIANDAY(f.last_inspected) as days_since_inspection,
    f.inspection_count,
    f.size_bytes,
    CASE
        WHEN JULIANDAY('now') - JULIANDAY(f.last_inspected) > 30 THEN 'VERY_STALE'
        WHEN JULIANDAY('now') - JULIANDAY(f.last_inspected) > 14 THEN 'STALE'
        WHEN JULIANDAY('now') - JULIANDAY(f.last_inspected) > 7 THEN 'AGING'
        ELSE 'FRESH'
    END as staleness
FROM files f
WHERE JULIANDAY('now') - JULIANDAY(f.last_inspected) > 7
ORDER BY days_since_inspection DESC
LIMIT 100
```

---

## Query 10: Attribute Analysis

**Use Case**: Extract custom attributes to understand render metadata (camera, render time, artist info).

**Example Scenario**: Editorial wants to know which camera was used for each shot.

```sql
-- Extract common custom attributes
SELECT
    f.file_id,
    f.file_path,
    MAX(CASE WHEN a.attr_name = 'cameraName' THEN a.value_text END) as camera,
    MAX(CASE WHEN a.attr_name = 'renderTime' THEN a.value_float END) as render_time_sec,
    MAX(CASE WHEN a.attr_name = 'artist' THEN a.value_text END) as artist,
    MAX(CASE WHEN a.attr_name = 'software' THEN a.value_text END) as render_software,
    f.last_inspected
FROM files f
LEFT JOIN attributes a ON f.file_id = a.file_id
GROUP BY f.file_id
HAVING camera IS NOT NULL OR render_time_sec IS NOT NULL
ORDER BY f.last_inspected DESC
LIMIT 50
```

**Expected Output**:
```
file_id | file_path | camera | render_time_sec | artist | render_software
--------|-----------|--------|-----------------|--------|------------------
f001    | shot_001.exr | CAM_A | 3245.5 | john_d | Arnold 7.1.2
f002    | shot_002.exr | CAM_B | 2156.3 | jane_s | RenderMan 25.0
```

---

## Performance Tips

1. **Use indexes**: Ensure these columns are indexed:
   - `files.file_path_normalized` (B-tree)
   - `files.is_deep` (bitmap)
   - `parts.compression` (B-tree)
   - `validation_results.severity` (bitmap)
   - `validation_results.policy_id` (B-tree)

2. **Partition large tables**: For >1M files, partition by date range:
   ```sql
   -- Queries should include date filter
   WHERE f.last_inspected >= DATE('now', '-90 days')
   ```

3. **Materialize views**: Pre-compute common aggregations:
   ```sql
   CREATE TABLE file_summaries_daily AS
   SELECT DATE(f.last_inspected) as date,
          COUNT(*) as file_count,
          SUM(f.size_bytes) as total_gb,
          ...
   FROM files f
   GROUP BY DATE(f.last_inspected)
   ```

4. **Use LIMIT**: Always limit result sets in interactive queries (shown in all examples above)

5. **Vector queries**: For similarity searches, use `DISTANCE()` function with appropriate metrics:
   - **Cosine**: Best for normalized vectors (metadata_embedding)
   - **Euclidean**: Best for structured data (channel_fingerprint)
   - **Dot product**: Fastest for approximate searches

---

## See Also

- [VECTOR_STRATEGY.md](VECTOR_STRATEGY.md) - Embedding computation and vector queries
- [SCHEMA_EVOLUTION.md](SCHEMA_EVOLUTION.md) - Schema updates and migrations
- [TROUBLESHOOTING.md](TROUBLESHOOTING.md) - Query debugging and performance issues
