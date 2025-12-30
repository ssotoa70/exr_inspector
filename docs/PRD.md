# Product Requirements Document (PRD)
## Project: **exr-inspector**

**Purpose:**  
Authoritative OpenEXR introspection, validation, and analysis tool for high-end VFX, Animation, and Media & Entertainment pipelines (e.g., Pixar, DreamWorks–class environments). Must run as a serverless Python function compatible with VAST DataEngine and persist extracted information to VAST DataBase.

---

## 1. Problem Statement

Modern studio pipelines rely heavily on **OpenEXR** for HDR imagery, deep data, and multi-part workflows. Existing tools are fragmented and insufficient:

- Partial or lossy metadata extraction
- Inconsistent handling of multipart and deep EXRs
- Unsafe pixel inspection for very large assets
- No standardized validation against studio policies
- Poor machine-readability for automation and CI

Studios need a **single, deterministic, scriptable tool** that can extract, validate, and optionally analyze OpenEXR files safely and completely.

---

## 2. Goals & Non-Goals

### 2.1 Goals

1. **Complete Metadata Extraction**
   - Lossless extraction of all EXR attributes
   - Preserve original data types and values

2. **Safe, Scalable Pixel Analysis**
   - Streaming-based processing
   - Explicit opt-in for expensive operations

3. **Production Validation**
   - Detect common pipeline and policy violations
   - Configurable per-studio / per-show rules

4. **Pipeline-Friendly Output**
   - Stable, deterministic JSON schema
   - Designed for automation and indexing
   - Persistable in VAST DataBase for downstream analytics

5. **Extensible Architecture**
   - Plugin-based design
   - Future-proof for new EXR features and workflows
   - Deployable as VAST DataEngine serverless Python function

---

### 2.2 Non-Goals (v1)

- Image display or preview
- Writing or modifying EXR files
- Color transforms or LUT application
- Replacing DCC-native tools (Nuke, Houdini, etc.)

---

## 3. Target Users

| Persona | Needs |
|------|------|
| Pipeline TD | Automated validation, metadata harvesting |
| Rendering Engineer | Debug multipart / deep EXRs |
| Asset Manager | Provenance, auditing, metadata indexing |
| Farm / CI Systems | Fast, deterministic checks |
| R&D / ML Teams | Structured metadata for analytics and AI |

---

## 4. Functional Requirements

---

### 4.1 Input Handling

- Single EXR file input
- Recursive directory processing (`--recursive`)
- Graceful handling of malformed or partially corrupted files
- Explicit detection of:
  - Scanline vs tiled
  - Multipart
  - Deep data
  - Multi-view / stereo

--- 

### 4.1.1 DataEngine Execution Requirements

- Compatible with VAST DataEngine serverless Python functions (stateless, event-driven)
- Designed to execute compute where data resides to minimize data movement
- Accept triggers from file/object updates to kick off inspection runs

---

### 4.2 Metadata Extraction (Core)

Extract all metadata **without loss**.

#### File-Level
- File path
- File size
- Modification time
- EXR version
- Multipart count
- Deep flag

#### Per-Part / Subimage
- part name
- view name
- dataWindow
- displayWindow
- pixelAspectRatio
- lineOrder
- compression
- tiling information

#### Channels
- Channel name (layered)
- Data type (half / float / uint)
- Sampling rates (x, y)
- Linearity (if inferable)

#### Attributes
- Preserve:
  - Original type
  - Raw value
- Supported attribute categories:
  - Scalars (int, float, string)
  - Arrays
  - Vectors (v2f, v3f)
  - Boxes (box2i, box2f)
  - Matrices
  - Timecode / keycode
  - Opaque / binary blobs (base64 encoded)

---

### 4.3 Pixel Statistics (Optional)

Enabled only via explicit flags.

- Per-channel statistics:
  - Min / Max
  - Mean
  - Standard deviation
  - NaN / Inf counts
- Streaming scanline or tile reads only
- Configurable sampling stride
- Deep EXR handling:
  - Detect deep data
  - Refuse stats unless `--deep-stats`
  - Flattening support deferred to future versions

---

### 4.4 Validation Framework

Built-in validation categories:

- **Structural**
  - Invalid or inverted windows
  - Missing required attributes

- **Channel Policy**
  - Required channels missing
  - Unexpected bit depths or channel types

- **Compression Policy**
  - Unsupported or non-standard compression

- **Color Management**
  - Missing chromaticities
  - Invalid primaries / white points

- **Naming Conventions**
  - Layer and channel naming rules

- **Multipart Expectations**
  - Unexpected multipart usage

Validation output:
- Severity: PASS / WARN / FAIL
- Stable machine-readable codes
- Human-readable messages

---

### 4.5 Persistence to VAST DataBase

- Store extracted metadata, stats (if enabled), and validation results in VAST DataBase
- Support transactional writes for consistency and auditing
- Enable analytical queries over structured EXR metadata for pipeline and AI workloads
- Allow deduplication or idempotent upserts keyed by file path + mtime + hash (tbd)

---

## 5. Output Requirements

### 5.1 JSON Schema (Stable)

```json
{
  "file": {},
  "parts": [],
  "channels": [],
  "attributes": {},
  "stats": {},
  "validation": {}
}
```

### 5.3 Future Fields (v1.1+)

- **Provenance:** `source_app`, `source_version`, `render_engine`, `render_engine_version`, `artist`, `dept`, `show`, `sequence`, `shot`, `asset`, `task`, `frame`, `frame_range`
- **Color & Imaging:** `colorspace`, `chromaticities`, `white_luminance`, `adopted_neutral`, `ocio_config`, `ocio_colorspace`, `display`, `view`
- **Render Metadata:** `camera_fov`, `camera_transform`, `lens`, `aperture`, `focal_length`, `render_time_ms`, `sample_count`, `noise_threshold`
- **Layer Semantics:** `layer_role`, `lpe_tags`, `channel_purpose`
- **Deep Data:** `deep_sample_count`, `deep_min_samples`, `deep_max_samples`, `deep_sample_stats`
- **Integrity:** `header_hash`, `pixel_hash_sampled`, `file_hash`, `schema_version`, `tool_version`
- **Pipeline Validation:** `policy_id`, `policy_version`, `rule_id`, `severity`, `expected_value`, `actual_value`, `suggested_fix`
- **Performance:** `parse_time_ms`, `stats_time_ms`, `memory_peak_mb`
- **Access & Storage:** `storage_tier`, `filesystem`, `bucket`, `region`, `tenant_id`

### 5.2 Output Modes

- Standard output
- File output
- Pretty vs compact JSON
- JSON Lines support (future)

---

## 6. CLI Interface (v1)

```
exr-inspector input.exr \
  --meta \
  --stats \
  --validate \
  --schema-version 1 \
  --output result.json
```

### Core Flags

- `--meta` (default)
- `--stats`
- `--deep-stats`
- `--validate`
- `--policy policy.yaml`
- `--fail-on error|warn`

---

## 7. Architecture & Design

### 7.1 Core Technologies

- Primary backend: OpenImageIO
- Optional fallback: OpenEXR Python bindings
- Language: Python 3.10+
- Execution: VAST DataEngine serverless Python functions
- Storage: VAST DataBase for structured metadata, stats, and validation output

---

### 7.2 Internal Module Layout

```
exr_inspector/
├── reader/        # EXR I/O abstraction
├── schema/        # JSON schema & normalization
├── stats/         # Streaming statistics
├── validation/    # Policy & rule engine
├── cli/           # Command-line interface
├── storage/       # VAST DataBase persistence
├── plugins/       # Extension points
```

---

### 7.3 Plugin System (Forward-Looking)

- Validation plugins
- Statistics plugins
- Export plugins (DB, HTTP, AI pipelines)

---

## 8. Performance & Safety Requirements

- Never load full image unless explicitly requested
- Streaming reads only
- Configurable memory limits
- Deterministic output ordering
- Safe failure modes for CI and farms

---

## 9. Security & Compliance

- Read-only file access
- No execution of embedded metadata
- Safe handling of untrusted EXR files
- Deterministic behavior suitable for audits
- Use VAST DataBase access controls for stored metadata

---

## 10. Extensibility Roadmap

### Phase 2

- Policy authoring DSL
- Asset database export (ShotGrid, custom DBs)
- Header-only and sampled pixel hashing

### Phase 3

- Deep sample analytics
- EXR diffing
- AI/ML-ready metadata embeddings

---

## 11. Success Metrics

- 100% header parity with oiiotool --info
- Zero crashes on malformed EXRs
- Deterministic JSON across runs
- Adoption in automated pipeline workflows

---

## 12. Open Questions

1. Policy format: YAML vs JSON?
2. Default validation severity thresholds?
3. Minimum Python version per studio?
4. Deep EXR flattening strategy?
5. Required attributes per show or department?

---

Status: Draft  
Next Step: Define JSON schema v1 and implementation plan
