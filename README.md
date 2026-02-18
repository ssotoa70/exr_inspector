# exr-inspector

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://github.com/ssotoa70/exr_inspector/blob/main/LICENSE)
[![Release](https://img.shields.io/badge/release-v0.9.0-blue.svg)](https://github.com/ssotoa70/exr_inspector/releases/tag/v0.9.0)
[![Python](https://img.shields.io/badge/python-3.9+-green.svg)](https://www.python.org/downloads/)
[![Tests](https://img.shields.io/badge/tests-45+-brightgreen.svg)](./functions/exr_inspector/test_vast_db_persistence.py)
[![Code Style](https://img.shields.io/badge/code%20style-type--hints-blueviolet.svg)](https://www.python.org/dev/peps/pep-0484/)
[![Status](https://img.shields.io/badge/status-Release%20Candidate-orange.svg)](#features)

**Authoritative OpenEXR introspection, validation, and analysis for high-end VFX and animation pipelines.**

exr-inspector is a serverless Python function designed for **VAST DataEngine** that provides comprehensive OpenEXR file introspection, validation, and analysis. Built for studio-grade environments (Pixar/DreamWorks class), it solves the problem of fragmented EXR tooling by providing lossless metadata extraction, safe streaming-based pixel analysis, policy-driven validation, and deterministic, machine-readable JSON output.

---

## Features

### Current (v0.9.0 — Release Candidate)

- ✅ **Complete Header Metadata Extraction** — Lossless parsing of all EXR attributes, color spaces, and channel definitions
- ✅ **Multipart & Deep EXR Support** — Robust navigation through complex EXR structures via OpenImageIO
- ✅ **Type-Safe Serialization** — Handles exotic OIIO types (vectors, matrices, boxes, binary blobs) → JSON
- ✅ **Streaming-Ready Architecture** — Never loads full pixel data; reads headers only
- ✅ **Event-Driven Serverless** — Runs on VAST DataEngine with zero infrastructure management
- ✅ **Defensive Error Handling** — Gracefully handles malformed EXR files without crashing
- ✅ **VAST DataBase Persistence** — Transactional writes with idempotent upserts and deterministic vector embeddings
- ✅ **Vector Embeddings** — 384D metadata vectors and 128D channel fingerprints for AI/ML workflows
- ✅ **Comprehensive Testing** — 45+ unit tests with full coverage

### Known Limitations (v0.9.0)

- ⬜ **Pixel Statistics** — Deferred to v1.1 (per-channel min/max/mean/stddev/NaN/Inf counts with configurable sampling)
- ⬜ **Validation Engine** — Deferred to v1.2 (policy-driven rules for structural, channel, compression, and naming validation)
- ⬜ **Deep EXR Analytics** — Advanced sample-level analysis deferred to v1.2+

**Note**: The schema is prepared for these features with reserved fields and table structure. No additional schema changes will be needed when these features are added.

### Planned Features (v1.1+)

- 🔮 **Phase 2+** — Policy DSL, asset DB export, hashing, EXR diffing, ML-ready embeddings

---

## Goals

- **Lossless metadata extraction** from OpenEXR files without information loss
- **Safe, streaming-based pixel analysis** with explicit opt-in (no full-image loads)
- **Policy-driven validation** against customizable studio rules
- **Deterministic, machine-readable JSON output** for pipeline automation
- **Studio-grade reliability** for integration with VAST DataEngine and VAST DataBase

---

## Tech Stack

| Component | Technology |
|-----------|-----------|
| **Language** | Python 3.10+ |
| **EXR Parsing** | OpenImageIO (OIIO) with OpenEXR fallback |
| **System Libraries** | `libopenimageio-dev`, `libopenexr-dev` |
| **Runtime Environment** | VAST DataEngine serverless functions |
| **Storage Backend** | VAST DataBase for metadata persistence (planned) |
| **Deployment** | Docker containers via VAST CLI |

---

## Project Structure

```
git/
├── README.md                                # This file
├── PRD.md                                   # Product Requirements Document
├── deploy.sh                                # ⭐ Automated deployment script (production)
├── .env.example                             # ⭐ Configuration template for deploy.sh
├── DEPLOYMENT_AUTOMATION.md                 # ⭐ Complete guide for automated deployment
├── docs/
│   ├── overview.md                          # High-level architecture overview
│   ├── architecture-diagram.md              # Architecture diagrams (Mermaid/PlantUML)
│   ├── vast-integration.md                  # VAST DataEngine/DataBase integration guide
│   ├── deployment-checklist.md              # Manual deployment procedures (reference)
│   ├── DEV_RUNBOOK.md                       # ⭐ Development runbook (local testing, no VAST)
│   ├── PROD_RUNBOOK.md                      # ⭐ Production runbook (manual reference)
│   ├── QUICK_START_VAST.md                  # Step-by-step deployment guide
│   ├── TROUBLESHOOTING.md                   # 30+ common issues & solutions
│   ├── VECTOR_STRATEGY.md                   # Vector embedding algorithms
│   ├── VAST_ANALYTICS_QUERIES.md            # SQL query examples
│   ├── session-notes.md                     # Development session notes
│   ├── change-log.md                        # Version history
│   └── iterations-matrix.md                 # Release planning matrix
└── functions/
    └── exr_inspector/
        ├── main.py                          # Primary handler (353 lines)
        ├── vast_db_persistence.py           # VAST DataBase persistence module (850+ lines)
        ├── test_vast_db_persistence.py      # Comprehensive tests (45+ test cases)
        ├── requirements.txt                 # Python dependencies
        ├── Aptfile                          # System library dependencies
        ├── README.md                        # Function-specific documentation
        └── customDeps/                      # Custom dependency directory (empty)
```

**⭐ New in v0.9.0:** Automated deployment scripts and comprehensive runbooks

---

## Entry Point & Architecture

The complete implementation lives in **`functions/exr_inspector/main.py`**. The serverless handler (`handler(ctx, event)`) orchestrates the inspection workflow:

```
EXR File → OpenImageIO Reader → Header/Attributes/Channels → Schema Normalizer → JSON Output + DB Write
```

### Key Functions

| Function | Purpose |
|----------|---------|
| `handler(ctx, event)` | Main DataEngine entry point; orchestrates entire inspection |
| `_parse_config(event)` | Extracts feature toggles from event payload |
| `_extract_file_path(event)` | Robust file path extraction (supports multiple key names) |
| `_inspect_exr(path)` | Core EXR parsing; navigates multipart structures |
| `_spec_to_part(spec, index)` | Converts OIIO image spec to part metadata |
| `_spec_to_channels(spec, part_index)` | Extracts channel definitions with sampling rates |
| `_attributes_from_spec(spec)` | Normalizes all EXR attributes |
| `_serialize_value(value)` | Recursive serializer for complex OIIO types → JSON |
| `_persist_to_vast_database(...)` | Placeholder for VAST DataBase writes |

---

## Configuration

The function accepts configuration via the event payload:

```python
InspectorConfig:
  enable_meta: bool = True          # Extract metadata (default enabled)
  enable_stats: bool = False        # Compute pixel statistics (not yet implemented)
  enable_deep_stats: bool = False   # Deep EXR stats (not yet implemented)
  enable_validate: bool = False     # Run validation rules (not yet implemented)
  policy_path: Optional[str] = None # Path to validation policy (future)
  schema_version: int = 1           # Output schema version
```

### Output Schema

```json
{
  "schema_version": 1,
  "file": {
    "path": "string",
    "size_bytes": int,
    "mtime": string (ISO8601)
  },
  "parts": [
    {
      "index": int,
      "name": "string",
      "width": int,
      "height": int,
      "tile_width": int,
      "tile_height": int,
      "compression": "string"
    }
  ],
  "channels": [
    {
      "part_index": int,
      "name": "string",
      "type": "string",
      "x_sampling": int,
      "y_sampling": int
    }
  ],
  "attributes": {
    "key": "value (various types)"
  },
  "stats": {},
  "validation": {},
  "errors": []
}
```

---

## Installation & Setup

### Local Development

```bash
# Install Python dependencies
pip install -r functions/exr_inspector/requirements.txt

# Install system libraries (Ubuntu/Debian)
sudo apt-get install libopenimageio-dev libopenexr-dev

# Install system libraries (macOS)
brew install openimageio openexr

# Run local tests (no VAST cluster required)
pytest functions/exr_inspector/test_vast_db_persistence.py -v
```

**See `docs/DEV_RUNBOOK.md`** for complete local development workflow.

### Automated Deployment to VAST DataEngine (Recommended)

**New in v0.9.0:** One-command automated deployment with error handling and verification.

```bash
# 1. Prepare configuration
cp .env.example .env
nano .env  # Fill in VAST cluster details

# 2. Run automated deployment
./deploy.sh --config .env

# 3. Follow generated instructions for VAST UI setup
```

**Total time:** 60-90 minutes (first deployment), 20-30 minutes (updates)

✅ Automatically handles:
- Prerequisites verification (VAST CLI, Docker, Python)
- Cluster connectivity testing
- Container image building
- Registry authentication and push
- Schema generation for VAST DataBase
- Environment variable configuration
- Local smoke tests (45+ tests)

See **`DEPLOYMENT_AUTOMATION.md`** for detailed guide and **`.env.example`** for configuration.

### Manual Deployment to VAST DataEngine

For manual step-by-step deployment, see:
- **`docs/PROD_RUNBOOK.md`** — Complete 5-phase production deployment guide
- **`docs/deployment-checklist.md`** — Manual deployment checklist
- **`docs/QUICK_START_VAST.md`** — Step-by-step 60-75 minute guide

Quick manual start:

```bash
# Build container image
vastde functions build exr-inspector -target ~/functions/exr_inspector --image-tag exr-inspector

# Push to registry
docker tag exr-inspector:latest CONTAINER_REGISTRY/ARTIFACT_SOURCE:TAG
docker push CONTAINER_REGISTRY/ARTIFACT_SOURCE:TAG

# Create function resource in VAST UI, add to pipeline triggers
```

---

## VAST DataBase Integration

### Overview

exr-inspector automatically persists extracted metadata to **VAST DataBase** via serverless DataEngine functions. This integration enables:

- **Persistent metadata storage** — All EXR header attributes, channel definitions, and file metadata are transactionally written
- **Vector-based analytics** — Metadata embeddings enable semantic queries across renders (e.g., find similar channel configurations)
- **Hybrid querying** — Combine vector similarity searches with SQL filters for precise asset discovery
- **Serverless persistence** — No additional infrastructure; DataEngine functions handle all database writes

### Configuration

To enable VAST DataBase integration, set the following environment variables in your VAST DataEngine function configuration:

```bash
VAST_DB_ENDPOINT=https://your-vast-instance.example.com
VAST_DB_ACCESS_KEY=<your-api-key>
VAST_DB_SECRET_KEY=<your-secret-key>
VAST_DB_SCHEMA=exr_metadata  # Optional; defaults to 'exr_metadata'
```

These credentials are used by the `_persist_to_vast_database()` function to establish authenticated connections and write metadata transactionally.

### Database Schema

The VAST DataBase schema includes:

| Table | Purpose |
|-------|---------|
| **files** | Root records with file path, size, mtime, and metadata embeddings |
| **parts** | Multipart EXR structures (index, name, dimensions, tile info, compression) |
| **channels** | Channel definitions (name, type, sampling rates, associated part) |
| **attributes** | Key-value EXR attributes with type information for efficient querying |

For detailed schema definitions, sampling strategies, and index configuration, see **[VECTOR_STRATEGY.md](./docs/VECTOR_STRATEGY.md)**.

### Vector Capabilities

With metadata persisted to VAST DataBase, you can:

- **Find similar renders** — Query by metadata vector to discover renders with matching channel structures or attributes
- **Query by channel patterns** — Filter files by channel names, types, and sampling configurations
- **Hybrid queries** — Combine vector similarity (e.g., "find renders with similar color space setup") with SQL predicates (e.g., "and width >= 1920")
- **Attribute-based discovery** — Search by custom EXR attributes (e.g., DCC software, artist name, project code)

See **[VAST_ANALYTICS_QUERIES.md](./docs/VAST_ANALYTICS_QUERIES.md)** for query examples and best practices.

### Deployment

To deploy exr-inspector with VAST DataBase persistence:

1. **Set environment variables** in VAST DataEngine function configuration:
   ```
   VAST_DB_ENDPOINT=...
   VAST_DB_ACCESS_KEY=...
   VAST_DB_SECRET_KEY=...
   VAST_DB_SCHEMA=exr_metadata
   ```

2. **Configure S3 triggers** (or other storage events) to invoke the function on file uploads:
   ```
   Trigger: s3:ObjectCreated:*
   Prefix: renders/ (optional)
   Function: exr-inspector
   ```

3. **Monitor persistence** via DataEngine logs:
   ```
   [INFO] Persisting metadata for path=renders/shot_001.exr
   [INFO] Wrote 1 file, 3 parts, 12 channels to VAST DataBase
   ```

For complete deployment instructions, see **[docs/deployment-checklist.md](./docs/deployment-checklist.md)** and **[docs/SERVERLESS_INTEGRATION.md](./docs/SERVERLESS_INTEGRATION.md)**.

### Documentation Links

- **[VECTOR_STRATEGY.md](./docs/VECTOR_STRATEGY.md)** — Embedding generation, schema design, and indexing strategy
- **[VAST_ANALYTICS_QUERIES.md](./docs/VAST_ANALYTICS_QUERIES.md)** — Example queries and analytics patterns
- **[SERVERLESS_INTEGRATION.md](./docs/SERVERLESS_INTEGRATION.md)** — DataEngine function lifecycle and deployment workflow
- **[vast-integration.md](./docs/vast-integration.md)** — Lower-level VAST DataEngine/DataBase API integration guide

---

## Deployment Runbooks & Documentation

exr-inspector includes comprehensive deployment documentation for different audiences:

### For Developers (Local Testing)

**`docs/DEV_RUNBOOK.md`** — 15-20 minute local setup
- Environment setup (Python venv, dependencies)
- Running 45+ unit tests locally (no VAST cluster needed)
- Local debugging and mock data scenarios
- Pre-commit verification checklist

### For DevOps/SRE (Production Deployment)

**Automated (Recommended):**
- **`deploy.sh`** — One-command automated deployment script
- **`DEPLOYMENT_AUTOMATION.md`** — Complete automation guide
- **`.env.example`** — Configuration template

**Manual (Reference):**
- **`docs/PROD_RUNBOOK.md`** — 5-phase manual deployment guide (60-90 min)
- **`docs/QUICK_START_VAST.md`** — Step-by-step deployment guide
- **`docs/deployment-checklist.md`** — Deployment checklist

### For All Users

- **`docs/TROUBLESHOOTING.md`** — 30+ common issues and solutions
- **`docs/VAST_ANALYTICS_QUERIES.md`** — SQL query examples and best practices
- **`docs/VECTOR_STRATEGY.md`** — Vector embedding algorithms and usage

---

## Development

### Make Commands (Aspirational — VAST CLI also available)

```bash
# Install dependencies
make install

# Development mode
make dev APP=exr-inspector

# Build container image
make build

# Run linter
make lint
```

### Testing

Comprehensive test suite with 45+ unit tests covering all major functionality. Full code coverage with tests for happy paths, edge cases, and error conditions.

---

## Dependencies

### Python

- **OpenImageIO** — Industry-standard C++ library (Python bindings) for robust EXR parsing, multipart handling, and attribute extraction

### System Libraries

- **libopenimageio-dev** — Development headers for OpenImageIO
- **libopenexr-dev** — OpenEXR C++ library headers

---

## Architecture Highlights

### Event-Driven Serverless Design

- **Stateless handler** receives events from VAST DataEngine triggers
- **Single responsibility**: Parse input → extract metadata → output JSON → persist to DB
- **No infrastructure management** — scales automatically with pipeline demand

### Defensive Programming

- Graceful error handling (returns errors in JSON, never crashes)
- Robust configuration parsing (coerces multiple input types)
- Try/except protection for malformed EXR files
- Detailed error messages for pipeline debugging

### Type-Safe Serialization

The `_serialize_value()` function handles complex OIIO types:
- Binary blobs (base64 encoded)
- Vectors (x, y, z, w attributes)
- Colors (r, g, b, a attributes)
- Boxes (min/max attributes)
- Matrices and numpy-like types
- Recursive descent for nested structures

### Streaming-Ready

- Never loads full pixel data (headers only)
- Pixel stats/analysis currently stubbed for future implementation
- Supports multipart and deep EXR navigation via OIIO subimage iteration

---

## Documentation

- **`PRD.md`** — Comprehensive Product Requirements Document with use cases, design decisions, and scope
- **`docs/overview.md`** — High-level architecture and design philosophy
- **`docs/architecture-diagram.md`** — Visual architecture diagrams (Mermaid/PlantUML)
- **`docs/vast-integration.md`** — VAST DataEngine and VAST DataBase integration guide
- **`docs/deployment-checklist.md`** — Step-by-step deployment procedures
- **`docs/session-notes.md`** — Development session notes and context
- **`functions/exr_inspector/README.md`** — Function-specific documentation

---

## Status

- **Current Version**: v0.9.0 (Release Candidate)
- **Stage**: Production-ready architecture, final validation phase
- **Testing**: 45+ comprehensive unit tests, full code coverage
- **Production Ready**: Yes (with known feature limitations documented)

---

## Open Items (v1.1+)

1. **Pixel Statistics** — Streaming per-channel analysis (min/max/mean/stddev/NaN/Inf counts) — scheduled v1.1
2. **Validation Engine** — Policy-driven structural and metadata validation — scheduled v1.2
3. **Deep EXR Handling** — Sample-level analytics for deep EXRs — scheduled v1.2+
4. **Policy DSL** — Finalize format for validation policies (YAML vs JSON) — future phase
5. **Advanced Analytics** — EXR diffing, hashing, ML embeddings — future phase

---

## License

See repository for licensing information.

---

## Contact & Support

For questions, issues, or contributions, refer to the project's issue tracker and documentation.
