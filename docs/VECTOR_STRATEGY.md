# Vector Embedding Strategy for EXR Metadata

## Overview

The exr-inspector VAST Database integration uses deterministic vector embeddings to enable semantic similarity search across EXR files and their channel structures. This document explains how embeddings are computed, why we use deterministic (non-ML) embeddings, and how to query with vectors.

**Key Design Goal**: Enable fast semantic search without ML model dependencies or re-training overhead.

---

## Metadata Embedding (384D)

### How `metadata_embedding` Vectors Are Computed

The metadata embedding captures the overall characteristics of an EXR file as a normalized 384-dimensional vector.

#### Computation Steps

1. **Feature Extraction** (lines 108-119 in `vast_db_persistence.py`)
   - Extract normalized features from EXR metadata:
     - Channel count: `count / 64` (normalize to [0, 1])
     - Part count: `count / 16`
     - Deep flag: `0.0` or `1.0`
     - Tiled flag: `0.0` or `1.0`
     - Multi-view flag: `0.0` or `1.0`
     - Compression type: mapped to [0, 1] range using compression map

2. **Feature Vector**: 6 base features combined into initial vector

3. **Hash Expansion** (lines 122-132)
   - Complete payload JSON is hashed using SHA256
   - Hash digest is converted to float values via struct unpacking
   - Creates additional dimensions from payload content
   - Ensures different file structures produce different vectors

4. **Padding/Truncation** (lines 138-149)
   - If fewer than 384 values: pad with derived values
   - If more than 384 values: truncate to 384
   - Derived padding uses existing vector values to maintain semantic continuity

5. **Normalization** (lines 151-158)
   - L2 normalization: `v / ||v||_2`
   - Result: unit vector with magnitude ≈ 1.0
   - Edge case: degenerate vectors normalized to uniform distribution

#### Example

```python
from vast_db_persistence import compute_metadata_embedding

payload = {
    "file": {
        "path": "/renders/shot_001.exr",
        "multipart_count": 2,
        "is_deep": False,
        "size_bytes": 104857600,
    },
    "channels": [
        {"name": "R", "type": "float"},
        {"name": "G", "type": "float"},
        {"name": "B", "type": "float"},
        {"name": "A", "type": "float"},
    ],
    "parts": [
        {"compression": "piz", "is_tiled": True},
        {"compression": "zip", "is_tiled": False},
    ],
}

# Compute 384D embedding
embedding = compute_metadata_embedding(payload, embedding_dim=384)
print(len(embedding))  # Output: 384
print(sum(v * v for v in embedding) ** 0.5)  # Output: ~1.0 (normalized)
```

---

## Channel Fingerprint (128D)

### How `channel_fingerprint` Vectors Are Computed

The channel fingerprint characterizes the channel structure and composition of an EXR file.

#### Computation Steps

1. **Channel Feature Extraction** (lines 205-221 in `vast_db_persistence.py`)
   - Channel count: `count / 64`
   - Layer diversity: `unique_layers / channel_count`
   - X sampling average: `sum(x_sampling) / (channel_count * 2)`
   - Y sampling average: `sum(y_sampling) / (channel_count * 2)`
   - Data type distribution for each common type (float, half, uint32, uint8)

2. **Layer Detection**
   - Splits channel names on "." separator
   - Counts unique layer prefixes (e.g., "beauty" from "beauty.R")
   - Captures channel organization patterns

3. **Hash-Based Fingerprinting** (lines 237-247)
   - Hash all channel names together using MD5
   - Ensures exact channel composition is captured
   - Sensitive to both channel count AND names

4. **Vector Combination**
   - Concatenate feature values + hash-derived values
   - Pad or truncate to 128 dimensions

5. **Normalization**
   - L2 normalization to unit vector

#### Example

```python
from vast_db_persistence import compute_channel_fingerprint

channels = [
    {"name": "beauty.R", "type": "float", "x_sampling": 1, "y_sampling": 1},
    {"name": "beauty.G", "type": "float", "x_sampling": 1, "y_sampling": 1},
    {"name": "beauty.B", "type": "float", "x_sampling": 1, "y_sampling": 1},
    {"name": "beauty.A", "type": "float", "x_sampling": 1, "y_sampling": 1},
    {"name": "diffuse.R", "type": "half", "x_sampling": 1, "y_sampling": 1},
    {"name": "diffuse.G", "type": "half", "x_sampling": 1, "y_sampling": 1},
    {"name": "diffuse.B", "type": "half", "x_sampling": 1, "y_sampling": 1},
    {"name": "Z", "type": "float", "x_sampling": 1, "y_sampling": 1},
]

fingerprint = compute_channel_fingerprint(channels, embedding_dim=128)
print(len(fingerprint))  # Output: 128
```

---

## Why Deterministic Embeddings (Not ML-Based)

### Advantages of Deterministic Approach

1. **No External Dependencies**
   - No ML models to download or version-pin
   - No model serving overhead
   - No GPU requirements in serverless

2. **Deterministic and Reproducible**
   - Same file always produces same vector
   - Safe for idempotent operations (upserts)
   - Reproducible across versions (with version checks)

3. **Efficient for Serverless**
   - Compute embeddings in milliseconds
   - No warmup time or model loading
   - Minimal memory footprint
   - Cost-effective for high-volume pipelines

4. **Transparent and Debuggable**
   - No black-box behavior
   - Clear feature mappings
   - Easy to understand why files cluster together

5. **Schema Evolution Friendly**
   - Can evolve embeddings without recomputing all historical data
   - New features can be added to feature extraction
   - Old vectors remain valid (version tracked in metadata)

### Trade-Offs

- **Less semantic richness** than ML embeddings: captures structural characteristics rather than learned semantic patterns
- **Linear separability**: vectors don't automatically cluster semantically similar content
- **Manual feature engineering**: as EXR characteristics evolve, embedding logic must be updated

---

## Supported Distance Metrics

VAST Database supports three vector distance metrics for semantic search:

### 1. **Cosine Similarity** (Default for metadata)

Best for comparing normalized vectors (unit vectors).

- **Formula**: `1 - (A · B) / (||A|| * ||B||)`
- **Range**: [0, 2] (0 = identical, 2 = opposite)
- **Use case**: Finding renders with similar overall metadata characteristics
- **Performance**: O(n) per query, highly optimizable

```sql
-- Example: Find metadata-similar renders
SELECT file_id, file_path,
       DISTANCE(metadata_embedding, ?, 'cosine') as similarity
FROM files
WHERE DISTANCE(metadata_embedding, ?, 'cosine') < 0.3
ORDER BY similarity
LIMIT 10;
```

### 2. **Euclidean Distance** (Default for channels)

Best for spatial closeness.

- **Formula**: `sqrt(sum((A[i] - B[i])^2))`
- **Range**: [0, sqrt(2*d)] for d-dimensional unit vectors
- **Use case**: Finding similar channel structures
- **Performance**: O(n) per query

```sql
-- Example: Find renders with similar channel compositions
SELECT file_id, file_path,
       DISTANCE(channel_fingerprint, ?, 'euclidean') as distance
FROM channels
WHERE part_id IN (SELECT part_id FROM channels
                  WHERE DISTANCE(channel_fingerprint, ?, 'euclidean') < 0.5)
ORDER BY distance
LIMIT 10;
```

### 3. **Dot Product** (For advanced analysis)

Fast approximation of similarity for normalized vectors.

- **Formula**: `A · B` (inner product)
- **Range**: [-1, 1] for normalized vectors (1 = identical)
- **Use case**: Fast approximate nearest neighbors
- **Performance**: Fastest, hardware-accelerated on many systems

```sql
-- Example: Fast similarity search using dot product
SELECT file_id, file_path,
       DOT_PRODUCT(metadata_embedding, ?) as similarity_score
FROM files
WHERE DOT_PRODUCT(metadata_embedding, ?) > 0.85
ORDER BY similarity_score DESC
LIMIT 20;
```

---

## Vector Query Examples Using ADBC SQL

### Query 1: Find Similar Renders by Complete Metadata

```python
# In application code:
import pyarrow.compute as pc
from vastdb_sdk import Session

# Create query vector from reference file
reference_payload = {
    "file": {...},
    "channels": [...],
    "parts": [...],
}
query_vector = compute_metadata_embedding(reference_payload)

# Create VAST session and query
session = Session(endpoint="https://vast.example.com", ...)
files_table = session.table("exr_metadata.files")

# SQL query: find top 10 similar files
query = """
SELECT
    file_id,
    file_path,
    size_bytes,
    multipart_count,
    DISTANCE(metadata_embedding, ?, 'cosine') as similarity
FROM files
WHERE file_path_normalized != ?
ORDER BY DISTANCE(metadata_embedding, ?, 'cosine') ASC
LIMIT 10
"""

results = files_table.select(query, [
    query_vector,
    _normalize_path(reference_payload["file"]["path"]),
    query_vector,
])

for row in results:
    print(f"File: {row['file_path']}")
    print(f"  Similarity: {row['similarity']:.4f}")
    print(f"  Size: {row['size_bytes'] / 1024 / 1024:.1f} MB")
```

### Query 2: Find Renders with Similar Channel Structure

```python
# Build channel fingerprint for a reference
reference_channels = [
    {"name": "R", "type": "float", "x_sampling": 1, "y_sampling": 1},
    {"name": "G", "type": "float", "x_sampling": 1, "y_sampling": 1},
    {"name": "B", "type": "float", "x_sampling": 1, "y_sampling": 1},
    {"name": "A", "type": "float", "x_sampling": 1, "y_sampling": 1},
]
channel_fp = compute_channel_fingerprint(reference_channels)

# Query for similar channel structures
channels_table = session.table("exr_metadata.channels")
query = """
SELECT
    DISTINCT c.file_id,
    f.file_path,
    COUNT(*) as channel_count,
    DISTANCE(c.channel_fingerprint, ?, 'euclidean') as distance
FROM channels c
JOIN files f ON c.file_id = f.file_id
WHERE DISTANCE(c.channel_fingerprint, ?, 'euclidean') < 0.4
GROUP BY c.file_id, f.file_path
ORDER BY distance ASC
LIMIT 5
"""

results = channels_table.select(query, [channel_fp, channel_fp])
```

### Query 3: Batch Similarity Analysis

```python
# Find clusters of similar renders by metadata
# (Useful for detecting render engine differences)

query = """
WITH similarity_pairs AS (
    SELECT
        f1.file_id as file1_id,
        f2.file_id as file2_id,
        f1.file_path as file1_path,
        f2.file_path as file2_path,
        DISTANCE(f1.metadata_embedding, f2.metadata_embedding, 'cosine') as similarity
    FROM files f1
    CROSS JOIN files f2
    WHERE f1.file_id < f2.file_id
    AND DISTANCE(f1.metadata_embedding, f2.metadata_embedding, 'cosine') < 0.2
)
SELECT
    file1_path,
    file2_path,
    similarity
FROM similarity_pairs
ORDER BY similarity ASC
"""

results = files_table.select(query, [])
for row in results:
    print(f"{row['file1_path']} <-> {row['file2_path']}: {row['similarity']:.4f}")
```

---

## How to Find Similar Renders by Metadata

### Step-by-Step Guide

1. **Get Reference Embedding**
   ```python
   from vast_db_persistence import compute_metadata_embedding

   # Inspect reference file
   ref_payload = inspect_exr("/renders/reference.exr")
   ref_embedding = compute_metadata_embedding(ref_payload)
   ```

2. **Query VAST Database**
   ```python
   from vastdb_sdk import Session

   session = Session(endpoint="...", access_key="...", secret_key="...")
   files_table = session.table("exr_metadata.files")

   query = """
   SELECT file_id, file_path, multipart_count, is_deep,
          DISTANCE(metadata_embedding, ?, 'cosine') as sim
   FROM files
   ORDER BY sim ASC
   LIMIT 20
   """

   results = files_table.select(query, [ref_embedding])
   ```

3. **Filter Results**
   ```python
   # Keep only matches with similarity < 0.3 (high similarity)
   similar_files = [r for r in results if r['sim'] < 0.3]

   for f in similar_files:
       print(f"{f['file_path']}: similarity={f['sim']:.4f}")
   ```

---

## Performance Characteristics

### Embedding Computation

| Operation | Time | Notes |
|-----------|------|-------|
| `compute_metadata_embedding()` | <5ms | Independent of payload size (uses hash) |
| `compute_channel_fingerprint()` | <2ms | Linear in channel count, typically 10-100 channels |
| Feature extraction | <1ms | Minimal processing |
| L2 normalization | <1ms | Single pass over vector |

### Vector Query Performance

| Query Type | Time | Scale |
|-----------|------|-------|
| Single similarity lookup | <10ms | O(n) scan + distance calculation |
| Top-K search | 50-200ms | Returns K results from N records |
| Cross-join similarity | 5-60 seconds | O(n²) pairwise distances for N files |
| Indexed search (if supported) | <5ms | With B-tree index on file_path_normalized |

### Storage

| Vector Type | Storage | Notes |
|-----------|---------|-------|
| metadata_embedding (384D) | ~1.5 KB | 384 float32 values + metadata |
| channel_fingerprint (128D) | ~0.5 KB | 128 float32 values + metadata |
| Per-file overhead | ~2 KB | Including embeddings and denormalized fields |

### Scaling Considerations

- **10,000 files**: ~20 MB vector storage, queries <1 second
- **100,000 files**: ~200 MB vector storage, queries 1-5 seconds (may need indexing)
- **1,000,000 files**: ~2 GB vector storage, queries 10-60 seconds (requires optimized indexing/partitioning)

---

## Schema Versioning

Embeddings are versioned implicitly through:

1. **`schema_version`** field in files table (currently "1.0.0")
2. **`inspector_version`** field in files table (e.g., "1.2.3")

When embedding logic changes:
- Create new computation function with new dimension/method
- Query both old and new embeddings during migration period
- Update `schema_version` when embedding logic changes significantly
- Maintain backward compatibility query logic

---

## See Also

- [VAST_ANALYTICS_QUERIES.md](VAST_ANALYTICS_QUERIES.md) - Real-world analytics examples
- [SCHEMA_EVOLUTION.md](SCHEMA_EVOLUTION.md) - Schema versioning and migrations
- [TROUBLESHOOTING.md](TROUBLESHOOTING.md) - Common embedding issues
