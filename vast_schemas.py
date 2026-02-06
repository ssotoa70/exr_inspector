"""
VAST DataBase PyArrow Schema Definitions for EXR Inspector
===========================================================

Production-ready schema definitions for storing EXR metadata in VAST DataBase.

DESIGN PRINCIPLES:
-----------------
1. **Vector Storage**: Uses pa.list_(pa.float32()) for embeddings
   - VAST DataBase vector capabilities require list types, not custom types
   - Supports cosine, euclidean, and dot product distance metrics
   - Enables semantic search across metadata and channel structures

2. **Virtual Row Tracking**: vastdb_rowid column
   - Automatically managed by VAST DataBase
   - Use for UPDATE operations: WHERE vastdb_rowid = <id>
   - Never explicitly set or insert this column

3. **Raw JSON Preservation**: raw_output as string
   - Complete inspector JSON stored for migration safety
   - Enables schema evolution without data loss
   - Allows future extraction of fields not yet normalized

4. **Denormalization Strategy**: Query optimization
   - Common query fields duplicated (value_text, value_int, value_float)
   - Reduces JSON parsing overhead for frequent queries
   - Trade-off: storage for performance in serverless functions

5. **Schema Versioning**: Explicit version tracking
   - schema_version: tracks this schema definition version
   - inspector_version: tracks exr-inspector tool version
   - Enables safe schema migration and compatibility checks

USAGE PATTERN:
-------------
```python
from vastdb import VastdbConnector

# Initialize connection
connector = VastdbConnector(endpoint, access_key, secret_key)
bucket = connector.get_bucket("exr-metadata-prod")

# Create schema namespace
schema = bucket.create_schema("exr_metadata")

# Create tables
files_table = schema.create_table("files", FILES_SCHEMA)
parts_table = schema.create_table("parts", PARTS_SCHEMA)
channels_table = schema.create_table("channels", CHANNELS_SCHEMA)
attributes_table = schema.create_table("attributes", ATTRIBUTES_SCHEMA)
stats_table = schema.create_table("stats", STATS_SCHEMA)
validation_table = schema.create_table("validation_results", VALIDATION_RESULTS_SCHEMA)
```

VECTOR SEARCH EXAMPLE:
---------------------
```python
# Find similar metadata fingerprints (cosine similarity)
query_vector = [0.1, 0.2, ..., 0.512]  # 512-dimensional embedding
results = files_table.search(
    vector_column="metadata_embedding",
    query_vector=query_vector,
    metric="cosine",
    limit=10
)

# Find similar channel structures
channel_results = channels_table.search(
    vector_column="channel_fingerprint",
    query_vector=channel_vector,
    metric="euclidean",
    limit=5
)
```

UPDATE PATTERN:
--------------
```python
# Use vastdb_rowid for updates (not custom IDs)
files_table.update(
    values={"inspection_count": inspection_count + 1, "last_inspected": now},
    where=f"vastdb_rowid = {row_id}"
)
```

SCHEMA VERSION: 1.0.0
COMPATIBLE WITH: exr-inspector >= 1.0.0
"""

import pyarrow as pa
from datetime import datetime
from typing import Dict, List


# =============================================================================
# SCHEMA VERSION CONSTANTS
# =============================================================================

SCHEMA_VERSION = "1.0.0"
VECTOR_DIMENSION_METADATA = 512  # Metadata embedding dimension
VECTOR_DIMENSION_CHANNEL = 128   # Channel fingerprint dimension


# =============================================================================
# 1. FILES TABLE - Primary entity for each unique EXR file
# =============================================================================

FILES_SCHEMA = pa.schema([
    # Primary Identification
    pa.field("file_id", pa.string(), nullable=False, metadata={
        "description": "UUID v4 identifier for this file record",
        "example": "550e8400-e29b-41d4-a716-446655440000"
    }),

    # File Path Information
    pa.field("file_path", pa.string(), nullable=False, metadata={
        "description": "Original absolute file path as discovered",
        "example": "/mnt/renders/shot_010/beauty.0001.exr"
    }),
    pa.field("file_path_normalized", pa.string(), nullable=False, metadata={
        "description": "Normalized path for deduplication (lowercase, resolved symlinks)",
        "example": "/mnt/renders/shot_010/beauty.0001.exr"
    }),

    # Unique Content Identifier
    pa.field("header_hash", pa.string(), nullable=False, metadata={
        "description": "SHA256 hash of EXR header for change detection",
        "example": "a1b2c3d4e5f6...",
        "index": "btree"  # Index for fast lookups
    }),

    # File Metadata
    pa.field("size_bytes", pa.int64(), nullable=False, metadata={
        "description": "File size in bytes",
        "example": "104857600"
    }),
    pa.field("mtime", pa.timestamp("us", tz="UTC"), nullable=False, metadata={
        "description": "File modification time (UTC)",
        "example": "2024-01-15T10:30:00Z"
    }),

    # EXR Structure Information
    pa.field("multipart_count", pa.int32(), nullable=False, metadata={
        "description": "Number of parts in multipart EXR (1 for single-part)",
        "example": "4"
    }),
    pa.field("is_deep", pa.bool_(), nullable=False, metadata={
        "description": "True if any part is deep data",
        "example": "false"
    }),
    pa.field("is_tiled", pa.bool_(), nullable=False, metadata={
        "description": "True if any part uses tiled layout",
        "example": "true"
    }),

    # Vector Embedding for Semantic Search
    pa.field("metadata_embedding", pa.list_(pa.float32()), nullable=True, metadata={
        "description": f"Vectorized metadata fingerprint ({VECTOR_DIMENSION_METADATA}D)",
        "dimension": str(VECTOR_DIMENSION_METADATA),
        "purpose": "Semantic similarity search across file metadata",
        "vector_type": "dense",
        "distance_metric": "cosine"
    }),

    # Inspection Tracking
    pa.field("first_seen", pa.timestamp("us", tz="UTC"), nullable=False, metadata={
        "description": "When this file was first inspected",
        "example": "2024-01-15T10:30:00Z"
    }),
    pa.field("last_inspected", pa.timestamp("us", tz="UTC"), nullable=False, metadata={
        "description": "Most recent inspection timestamp",
        "example": "2024-01-20T14:45:00Z"
    }),
    pa.field("inspection_count", pa.int32(), nullable=False, metadata={
        "description": "Number of times this file has been inspected",
        "example": "3"
    }),

    # Version Tracking
    pa.field("schema_version", pa.string(), nullable=False, metadata={
        "description": "Version of this schema definition",
        "example": "1.0.0"
    }),
    pa.field("inspector_version", pa.string(), nullable=False, metadata={
        "description": "Version of exr-inspector tool used",
        "example": "1.2.3"
    }),

    # Raw Data Preservation
    pa.field("raw_output", pa.string(), nullable=False, metadata={
        "description": "Complete JSON output from exr-inspector (migration safety)",
        "purpose": "Enables schema evolution without data loss",
        "storage": "compressed_json_string"
    }),

    # Metadata for table schema
], metadata={
    "table_name": "files",
    "description": "Primary table storing unique EXR file records",
    "primary_key": "file_id",
    "unique_constraints": ["header_hash", "file_path_normalized"],
    "indexes": ["header_hash", "file_path_normalized", "mtime"]
})


# =============================================================================
# 2. PARTS TABLE - Individual parts within EXR files
# =============================================================================

PARTS_SCHEMA = pa.schema([
    # Primary Identification
    pa.field("part_id", pa.string(), nullable=False, metadata={
        "description": "UUID v4 identifier for this part record",
        "example": "660e8400-e29b-41d4-a716-446655440001"
    }),

    # Foreign Key Relationship
    pa.field("file_id", pa.string(), nullable=False, metadata={
        "description": "Reference to parent file record",
        "foreign_key": "files.file_id",
        "index": "btree"
    }),

    # Part Identification
    pa.field("part_index", pa.int32(), nullable=False, metadata={
        "description": "Zero-based index of this part (0 for single-part)",
        "example": "0"
    }),
    pa.field("part_name", pa.string(), nullable=True, metadata={
        "description": "Optional part name in multipart EXR",
        "example": "rgba"
    }),
    pa.field("view_name", pa.string(), nullable=True, metadata={
        "description": "Stereo view name if applicable",
        "example": "left"
    }),

    # Image Dimensions (stored as JSON strings for complex objects)
    pa.field("data_window", pa.string(), nullable=False, metadata={
        "description": "Data window as JSON: {xMin, yMin, xMax, yMax}",
        "example": '{"xMin": 0, "yMin": 0, "xMax": 1919, "yMax": 1079}',
        "format": "json"
    }),
    pa.field("display_window", pa.string(), nullable=False, metadata={
        "description": "Display window as JSON: {xMin, yMin, xMax, yMax}",
        "example": '{"xMin": 0, "yMin": 0, "xMax": 1919, "yMax": 1079}',
        "format": "json"
    }),

    # Image Properties
    pa.field("pixel_aspect_ratio", pa.float32(), nullable=False, metadata={
        "description": "Pixel aspect ratio (usually 1.0)",
        "example": "1.0"
    }),
    pa.field("line_order", pa.string(), nullable=False, metadata={
        "description": "Scanline order: INCREASING_Y, DECREASING_Y, RANDOM_Y",
        "example": "INCREASING_Y",
        "enum": ["INCREASING_Y", "DECREASING_Y", "RANDOM_Y"]
    }),
    pa.field("compression", pa.string(), nullable=False, metadata={
        "description": "Compression method",
        "example": "ZIP_COMPRESSION",
        "enum": ["NONE", "RLE", "ZIPS", "ZIP", "PIZ", "PXR24", "B44", "B44A", "DWAA", "DWAB"]
    }),

    # Layout Information
    pa.field("is_tiled", pa.bool_(), nullable=False, metadata={
        "description": "True if this part uses tiled layout",
        "example": "false"
    }),
    pa.field("tile_width", pa.int32(), nullable=True, metadata={
        "description": "Tile width (null if scanline)",
        "example": "64"
    }),
    pa.field("tile_height", pa.int32(), nullable=True, metadata={
        "description": "Tile height (null if scanline)",
        "example": "64"
    }),
    pa.field("tile_depth", pa.int32(), nullable=True, metadata={
        "description": "Tile depth for deep/volume data (null if 2D)",
        "example": "1"
    }),

    # Deep Data
    pa.field("is_deep", pa.bool_(), nullable=False, metadata={
        "description": "True if this part contains deep data",
        "example": "false"
    }),

], metadata={
    "table_name": "parts",
    "description": "Individual parts within EXR files (multipart support)",
    "primary_key": "part_id",
    "foreign_keys": ["file_id -> files.file_id"],
    "indexes": ["file_id", "part_index"],
    "unique_constraints": ["file_id + part_index"]
})


# =============================================================================
# 3. CHANNELS TABLE - Individual channels within parts
# =============================================================================

CHANNELS_SCHEMA = pa.schema([
    # Primary Identification
    pa.field("channel_id", pa.string(), nullable=False, metadata={
        "description": "UUID v4 identifier for this channel record",
        "example": "770e8400-e29b-41d4-a716-446655440002"
    }),

    # Foreign Key Relationships
    pa.field("file_id", pa.string(), nullable=False, metadata={
        "description": "Reference to parent file record",
        "foreign_key": "files.file_id",
        "index": "btree"
    }),
    pa.field("part_id", pa.string(), nullable=False, metadata={
        "description": "Reference to parent part record",
        "foreign_key": "parts.part_id",
        "index": "btree"
    }),

    # Channel Identification
    pa.field("channel_name", pa.string(), nullable=False, metadata={
        "description": "Full channel name (e.g., 'beauty.R', 'A')",
        "example": "beauty.R"
    }),
    pa.field("channel_type", pa.string(), nullable=False, metadata={
        "description": "Data type: HALF, FLOAT, UINT",
        "example": "HALF",
        "enum": ["HALF", "FLOAT", "UINT"]
    }),

    # Parsed Channel Components
    pa.field("layer_name", pa.string(), nullable=True, metadata={
        "description": "Layer prefix if present (e.g., 'beauty' from 'beauty.R')",
        "example": "beauty"
    }),
    pa.field("component_name", pa.string(), nullable=True, metadata={
        "description": "Component suffix (e.g., 'R', 'G', 'B', 'A', 'Z')",
        "example": "R"
    }),

    # Sampling Information
    pa.field("x_sampling", pa.int32(), nullable=False, metadata={
        "description": "Horizontal subsampling factor (usually 1)",
        "example": "1"
    }),
    pa.field("y_sampling", pa.int32(), nullable=False, metadata={
        "description": "Vertical subsampling factor (usually 1)",
        "example": "1"
    }),

    # Optional Metadata
    pa.field("linearity", pa.string(), nullable=True, metadata={
        "description": "Color linearity: linear, sRGB, Rec709, etc.",
        "example": "linear"
    }),

    # Vector Embedding for Channel Structure Search
    pa.field("channel_fingerprint", pa.list_(pa.float32()), nullable=True, metadata={
        "description": f"Vectorized channel structure fingerprint ({VECTOR_DIMENSION_CHANNEL}D)",
        "dimension": str(VECTOR_DIMENSION_CHANNEL),
        "purpose": "Find similar channel configurations across files",
        "vector_type": "dense",
        "distance_metric": "euclidean"
    }),

], metadata={
    "table_name": "channels",
    "description": "Individual channels within EXR parts",
    "primary_key": "channel_id",
    "foreign_keys": ["file_id -> files.file_id", "part_id -> parts.part_id"],
    "indexes": ["file_id", "part_id", "channel_name", "layer_name"],
    "unique_constraints": ["part_id + channel_name"]
})


# =============================================================================
# 4. ATTRIBUTES TABLE - Custom attributes from EXR headers
# =============================================================================

ATTRIBUTES_SCHEMA = pa.schema([
    # Primary Identification
    pa.field("attribute_id", pa.string(), nullable=False, metadata={
        "description": "UUID v4 identifier for this attribute record",
        "example": "880e8400-e29b-41d4-a716-446655440003"
    }),

    # Foreign Key Relationships
    pa.field("file_id", pa.string(), nullable=False, metadata={
        "description": "Reference to parent file record",
        "foreign_key": "files.file_id",
        "index": "btree"
    }),
    pa.field("part_id", pa.string(), nullable=True, metadata={
        "description": "Reference to part (null for file-level attributes)",
        "foreign_key": "parts.part_id",
        "index": "btree"
    }),

    # Attribute Identification
    pa.field("attr_name", pa.string(), nullable=False, metadata={
        "description": "Attribute name (e.g., 'owner', 'comments', 'chromaticities')",
        "example": "owner",
        "index": "btree"
    }),
    pa.field("attr_type", pa.string(), nullable=False, metadata={
        "description": "Attribute type (e.g., 'string', 'int', 'float', 'v2i', 'box2i')",
        "example": "string"
    }),

    # Raw Value (always preserved as JSON)
    pa.field("value_json", pa.string(), nullable=False, metadata={
        "description": "Complete attribute value as JSON string",
        "example": '{"value": "John Doe", "type": "string"}',
        "format": "json"
    }),

    # Denormalized Values for Query Optimization
    pa.field("value_text", pa.string(), nullable=True, metadata={
        "description": "String value (denormalized for text queries)",
        "example": "John Doe",
        "purpose": "Avoid JSON parsing for common string queries"
    }),
    pa.field("value_int", pa.int64(), nullable=True, metadata={
        "description": "Integer value (denormalized for numeric queries)",
        "example": "42",
        "purpose": "Avoid JSON parsing for common integer queries"
    }),
    pa.field("value_float", pa.float64(), nullable=True, metadata={
        "description": "Float value (denormalized for numeric queries)",
        "example": "3.14159",
        "purpose": "Avoid JSON parsing for common float queries"
    }),

], metadata={
    "table_name": "attributes",
    "description": "Custom attributes from EXR headers (file and part level)",
    "primary_key": "attribute_id",
    "foreign_keys": ["file_id -> files.file_id", "part_id -> parts.part_id"],
    "indexes": ["file_id", "part_id", "attr_name"],
    "unique_constraints": ["file_id + part_id + attr_name"]
})


# =============================================================================
# 5. STATS TABLE - Pixel statistics (prepared for future implementation)
# =============================================================================

STATS_SCHEMA = pa.schema([
    # Primary Identification
    pa.field("stat_id", pa.string(), nullable=False, metadata={
        "description": "UUID v4 identifier for this statistics record",
        "example": "990e8400-e29b-41d4-a716-446655440004"
    }),

    # Foreign Key Relationships
    pa.field("file_id", pa.string(), nullable=False, metadata={
        "description": "Reference to parent file record",
        "foreign_key": "files.file_id",
        "index": "btree"
    }),
    pa.field("part_id", pa.string(), nullable=False, metadata={
        "description": "Reference to parent part record",
        "foreign_key": "parts.part_id",
        "index": "btree"
    }),
    pa.field("channel_id", pa.string(), nullable=False, metadata={
        "description": "Reference to parent channel record",
        "foreign_key": "channels.channel_id",
        "index": "btree"
    }),

    # Statistical Values
    pa.field("min_value", pa.float64(), nullable=True, metadata={
        "description": "Minimum pixel value in channel",
        "example": "0.0"
    }),
    pa.field("max_value", pa.float64(), nullable=True, metadata={
        "description": "Maximum pixel value in channel",
        "example": "1.0"
    }),
    pa.field("mean_value", pa.float64(), nullable=True, metadata={
        "description": "Mean pixel value in channel",
        "example": "0.5"
    }),
    pa.field("stddev_value", pa.float64(), nullable=True, metadata={
        "description": "Standard deviation of pixel values",
        "example": "0.25"
    }),

    # Quality Indicators
    pa.field("nan_count", pa.int64(), nullable=True, metadata={
        "description": "Number of NaN pixels detected",
        "example": "0"
    }),
    pa.field("inf_count", pa.int64(), nullable=True, metadata={
        "description": "Number of infinite pixels detected",
        "example": "0"
    }),

    # Sampling Information
    pa.field("sample_stride", pa.int32(), nullable=True, metadata={
        "description": "Pixel stride used for sampling (1 = every pixel)",
        "example": "10"
    }),
    pa.field("sampled_pixel_count", pa.int64(), nullable=True, metadata={
        "description": "Number of pixels actually sampled",
        "example": "207360"
    }),

    # Content Fingerprint
    pa.field("pixel_hash_sampled", pa.string(), nullable=True, metadata={
        "description": "Hash of sampled pixel data for content verification",
        "example": "a1b2c3d4...",
        "purpose": "Detect pixel data changes without full comparison"
    }),

    # Computation Metadata
    pa.field("computed_at", pa.timestamp("us", tz="UTC"), nullable=False, metadata={
        "description": "When these statistics were computed",
        "example": "2024-01-15T10:30:00Z"
    }),
    pa.field("computation_time_ms", pa.int32(), nullable=True, metadata={
        "description": "Time taken to compute statistics (milliseconds)",
        "example": "150"
    }),

], metadata={
    "table_name": "stats",
    "description": "Pixel statistics for channels (future feature)",
    "primary_key": "stat_id",
    "foreign_keys": [
        "file_id -> files.file_id",
        "part_id -> parts.part_id",
        "channel_id -> channels.channel_id"
    ],
    "indexes": ["file_id", "part_id", "channel_id"],
    "unique_constraints": ["channel_id + computed_at"],
    "status": "prepared_for_future"
})


# =============================================================================
# 6. VALIDATION_RESULTS TABLE - Policy validation results
# =============================================================================

VALIDATION_RESULTS_SCHEMA = pa.schema([
    # Primary Identification
    pa.field("validation_id", pa.string(), nullable=False, metadata={
        "description": "UUID v4 identifier for this validation record",
        "example": "aa0e8400-e29b-41d4-a716-446655440005"
    }),

    # Foreign Key Relationship
    pa.field("file_id", pa.string(), nullable=False, metadata={
        "description": "Reference to parent file record",
        "foreign_key": "files.file_id",
        "index": "btree"
    }),

    # Policy Context
    pa.field("policy_id", pa.string(), nullable=False, metadata={
        "description": "Identifier of validation policy used",
        "example": "vfx_standard_v2",
        "index": "btree"
    }),
    pa.field("policy_version", pa.string(), nullable=False, metadata={
        "description": "Version of validation policy",
        "example": "2.1.0"
    }),
    pa.field("rule_id", pa.string(), nullable=False, metadata={
        "description": "Specific rule identifier within policy",
        "example": "compression_check",
        "index": "btree"
    }),

    # Validation Result
    pa.field("severity", pa.string(), nullable=False, metadata={
        "description": "Result severity level",
        "example": "WARN",
        "enum": ["PASS", "WARN", "FAIL"],
        "index": "btree"
    }),
    pa.field("status", pa.string(), nullable=False, metadata={
        "description": "Detailed status code",
        "example": "SUBOPTIMAL_COMPRESSION"
    }),
    pa.field("message", pa.string(), nullable=False, metadata={
        "description": "Human-readable validation message",
        "example": "Compression type NONE detected; recommend ZIP for better efficiency"
    }),

    # Validation Details
    pa.field("expected_value", pa.string(), nullable=True, metadata={
        "description": "Expected value as JSON",
        "example": '{"compression": ["ZIP", "DWAA", "DWAB"]}',
        "format": "json"
    }),
    pa.field("actual_value", pa.string(), nullable=True, metadata={
        "description": "Actual value found as JSON",
        "example": '{"compression": "NONE"}',
        "format": "json"
    }),
    pa.field("suggested_fix", pa.string(), nullable=True, metadata={
        "description": "Suggested remediation action",
        "example": "Re-render with ZIP_COMPRESSION or use exrconvert"
    }),

    # Timestamp
    pa.field("validated_at", pa.timestamp("us", tz="UTC"), nullable=False, metadata={
        "description": "When this validation was performed",
        "example": "2024-01-15T10:30:00Z"
    }),

], metadata={
    "table_name": "validation_results",
    "description": "Results from policy validation checks",
    "primary_key": "validation_id",
    "foreign_keys": ["file_id -> files.file_id"],
    "indexes": ["file_id", "policy_id", "severity", "validated_at"],
    "unique_constraints": ["file_id + policy_id + rule_id + validated_at"]
})


# =============================================================================
# SCHEMA REGISTRY - Central access point for all schemas
# =============================================================================

SCHEMA_REGISTRY: Dict[str, pa.Schema] = {
    "files": FILES_SCHEMA,
    "parts": PARTS_SCHEMA,
    "channels": CHANNELS_SCHEMA,
    "attributes": ATTRIBUTES_SCHEMA,
    "stats": STATS_SCHEMA,
    "validation_results": VALIDATION_RESULTS_SCHEMA,
}


# =============================================================================
# TABLE CREATION HELPERS
# =============================================================================

def create_exr_metadata_tables(bucket, schema_name: str = "exr_metadata") -> Dict[str, any]:
    """
    Create all EXR metadata tables in VAST DataBase.

    Args:
        bucket: VAST DataBase bucket instance
        schema_name: Name for the schema namespace

    Returns:
        Dictionary mapping table names to table instances

    Example:
        >>> from vastdb import VastdbConnector
        >>> connector = VastdbConnector(endpoint, access_key, secret_key)
        >>> bucket = connector.get_bucket("exr-metadata-prod")
        >>> tables = create_exr_metadata_tables(bucket)
        >>> files_table = tables["files"]
    """
    # Create schema namespace
    schema = bucket.create_schema(schema_name)

    # Create tables in dependency order
    tables = {}

    # 1. Files (no dependencies)
    tables["files"] = schema.create_table("files", FILES_SCHEMA)

    # 2. Parts (depends on files)
    tables["parts"] = schema.create_table("parts", PARTS_SCHEMA)

    # 3. Channels (depends on files and parts)
    tables["channels"] = schema.create_table("channels", CHANNELS_SCHEMA)

    # 4. Attributes (depends on files and parts)
    tables["attributes"] = schema.create_table("attributes", ATTRIBUTES_SCHEMA)

    # 5. Stats (depends on files, parts, channels)
    tables["stats"] = schema.create_table("stats", STATS_SCHEMA)

    # 6. Validation Results (depends on files)
    tables["validation_results"] = schema.create_table(
        "validation_results",
        VALIDATION_RESULTS_SCHEMA
    )

    return tables


def get_schema_info() -> Dict[str, any]:
    """
    Get comprehensive schema information for documentation and validation.

    Returns:
        Dictionary containing schema version, tables, and metadata
    """
    return {
        "schema_version": SCHEMA_VERSION,
        "vector_dimensions": {
            "metadata_embedding": VECTOR_DIMENSION_METADATA,
            "channel_fingerprint": VECTOR_DIMENSION_CHANNEL,
        },
        "tables": {
            name: {
                "schema": schema,
                "num_fields": len(schema),
                "primary_key": schema.metadata.get(b"primary_key", b"").decode("utf-8"),
                "description": schema.metadata.get(b"description", b"").decode("utf-8"),
            }
            for name, schema in SCHEMA_REGISTRY.items()
        },
        "dependencies": {
            "parts": ["files"],
            "channels": ["files", "parts"],
            "attributes": ["files", "parts"],
            "stats": ["files", "parts", "channels"],
            "validation_results": ["files"],
        }
    }


# =============================================================================
# EXAMPLE USAGE AND PATTERNS
# =============================================================================

if __name__ == "__main__":
    """
    Example usage patterns for VAST DataBase integration.

    NOTE: This is demonstration code. In production, use proper configuration
    management and error handling.
    """

    # Print schema information
    print("=" * 80)
    print("EXR Inspector VAST DataBase Schema Definitions")
    print("=" * 80)
    print(f"\nSchema Version: {SCHEMA_VERSION}")
    print(f"Total Tables: {len(SCHEMA_REGISTRY)}")

    info = get_schema_info()
    print(f"\nVector Dimensions:")
    for name, dim in info["vector_dimensions"].items():
        print(f"  - {name}: {dim}D")

    print(f"\nTable Summary:")
    for table_name, table_info in info["tables"].items():
        print(f"\n  {table_name.upper()}")
        print(f"    Fields: {table_info['num_fields']}")
        print(f"    Primary Key: {table_info['primary_key']}")
        print(f"    Description: {table_info['description']}")

    # Example: Table creation pattern
    print("\n" + "=" * 80)
    print("TABLE CREATION PATTERN")
    print("=" * 80)
    print("""
from vastdb import VastdbConnector
from vast_schemas import create_exr_metadata_tables

# Initialize VAST connection
connector = VastdbConnector(
    endpoint="https://vast-endpoint.example.com",
    access_key="your-access-key",
    secret_key="your-secret-key"
)

# Get or create bucket
bucket = connector.get_bucket("exr-metadata-prod")

# Create all tables
tables = create_exr_metadata_tables(bucket, schema_name="exr_metadata")

# Access individual tables
files_table = tables["files"]
channels_table = tables["channels"]
    """)

    # Example: Insert pattern
    print("\n" + "=" * 80)
    print("INSERT PATTERN")
    print("=" * 80)
    print("""
import uuid
from datetime import datetime

# Prepare file record
file_record = {
    "file_id": str(uuid.uuid4()),
    "file_path": "/mnt/renders/shot_010/beauty.0001.exr",
    "file_path_normalized": "/mnt/renders/shot_010/beauty.0001.exr",
    "header_hash": "a1b2c3d4e5f6...",
    "size_bytes": 104857600,
    "mtime": datetime.now(),
    "multipart_count": 1,
    "is_deep": False,
    "is_tiled": True,
    "metadata_embedding": [0.1] * 512,  # 512D vector
    "first_seen": datetime.now(),
    "last_inspected": datetime.now(),
    "inspection_count": 1,
    "schema_version": "1.0.0",
    "inspector_version": "1.2.3",
    "raw_output": '{"file": {...}}',  # Complete JSON
}

# Insert into files table
files_table.insert([file_record])
    """)

    # Example: Vector search pattern
    print("\n" + "=" * 80)
    print("VECTOR SEARCH PATTERN")
    print("=" * 80)
    print("""
# Search for similar metadata fingerprints
query_embedding = [0.1, 0.2, ...] # 512D vector from new file

similar_files = files_table.search(
    vector_column="metadata_embedding",
    query_vector=query_embedding,
    metric="cosine",  # or "euclidean", "dot_product"
    limit=10
)

for result in similar_files:
    print(f"File: {result['file_path']}, Similarity: {result['_distance']}")

# Search for similar channel structures
channel_fingerprint = [0.3, 0.4, ...] # 128D vector

similar_channels = channels_table.search(
    vector_column="channel_fingerprint",
    query_vector=channel_fingerprint,
    metric="euclidean",
    limit=5,
    filter="layer_name = 'beauty'"  # Optional filter
)
    """)

    # Example: Update pattern
    print("\n" + "=" * 80)
    print("UPDATE PATTERN (using vastdb_rowid)")
    print("=" * 80)
    print("""
# Query to get vastdb_rowid
results = files_table.query(
    select=["vastdb_rowid", "inspection_count"],
    where="file_path_normalized = '/mnt/renders/shot_010/beauty.0001.exr'"
)

for row in results:
    row_id = row["vastdb_rowid"]
    current_count = row["inspection_count"]

    # Update using vastdb_rowid
    files_table.update(
        values={
            "inspection_count": current_count + 1,
            "last_inspected": datetime.now()
        },
        where=f"vastdb_rowid = {row_id}"
    )
    """)

    # Example: Complex query pattern
    print("\n" + "=" * 80)
    print("COMPLEX QUERY PATTERN")
    print("=" * 80)
    print("""
# Find all tiled EXR files with DWAA compression from last week
from datetime import datetime, timedelta

week_ago = datetime.now() - timedelta(days=7)

results = files_table.query(
    select=["file_path", "size_bytes", "mtime"],
    where=f'''
        is_tiled = true
        AND mtime >= '{week_ago.isoformat()}'
    '''
)

# Join with parts to check compression
for file_row in results:
    parts = parts_table.query(
        select=["compression", "part_name"],
        where=f"file_id = '{file_row['file_id']}' AND compression = 'DWAA'"
    )

    if parts:
        print(f"File: {file_row['file_path']}")
        print(f"  Size: {file_row['size_bytes'] / 1024 / 1024:.2f} MB")
        print(f"  Parts with DWAA: {len(parts)}")
    """)

    print("\n" + "=" * 80)
    print("SCHEMA EVOLUTION NOTES")
    print("=" * 80)
    print("""
WHY DESIGN CHOICES MATTER:

1. Vector Storage as pa.list_(pa.float32()):
   - VAST DataBase requires list types for vector operations
   - DO NOT use custom types or nested structs
   - Dimension metadata is informational only
   - Enable vector search with .search() method

2. vastdb_rowid for Updates:
   - Virtual column automatically managed by VAST
   - ALWAYS use WHERE vastdb_rowid = <id> for updates
   - Never insert or set this column explicitly
   - More efficient than custom ID lookups

3. Raw JSON as String:
   - Complete exr-inspector output preserved
   - Enables schema migration without data loss
   - Extract new fields later without re-scanning files
   - Trade storage for future flexibility

4. Denormalized Query Fields:
   - value_text, value_int, value_float avoid JSON parsing
   - Serverless functions are stateless - parsing overhead matters
   - Storage is cheap, computation time is expensive
   - Update ALL denormalized fields together

5. Schema Versioning Strategy:
   - schema_version tracks this definition version
   - inspector_version tracks tool version
   - Check compatibility before processing
   - Support multiple schema versions simultaneously
   - Migrate data incrementally, not all at once

FUTURE EVOLUTION:
- Add new optional fields (nullable=True)
- Create new tables without modifying existing ones
- Use raw_output to backfill new fields
- Version-aware query logic handles mixed versions
- Deprecate old tables after full migration
    """)
