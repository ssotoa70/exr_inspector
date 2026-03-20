# exr-inspector

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://github.com/ssotoa70/exr_inspector/blob/main/LICENSE)
[![Release](https://img.shields.io/badge/release-v0.9.0-blue.svg)](https://github.com/ssotoa70/exr_inspector/releases/tag/v0.9.0)
[![Python](https://img.shields.io/badge/python-3.9+-green.svg)](https://www.python.org/downloads/)
[![Tests](https://img.shields.io/badge/tests-45+-brightgreen.svg)](./functions/exr_inspector/test_vast_db_persistence.py)
[![Status](https://img.shields.io/badge/status-Release%20Candidate-orange.svg)](#status)

**Authoritative OpenEXR introspection, validation, and analysis for high-end VFX and animation pipelines.**

exr-inspector is a serverless Python function for **VAST DataEngine** that provides lossless EXR metadata extraction, deterministic vector embeddings, and transactional persistence to VAST DataBase. Built for studio-grade environments (Pixar/DreamWorks class).

---

## Quick Start

```bash
# 1. Clone and install
git clone https://github.com/ssotoa70/exr_inspector.git
cd exr_inspector
pip install -r functions/exr_inspector/requirements.txt

# 2. Install system libraries (macOS / Ubuntu)
brew install openimageio openexr          # macOS
# sudo apt-get install libopenimageio-dev libopenexr-dev  # Ubuntu

# 3. Run tests (no VAST cluster required)
pytest functions/exr_inspector/test_vast_db_persistence.py -v

# 4. Build container image (see docs/DEPLOY.md for full guide)
brew install buildpacks/tap/pack          # one time
docker pull docker.selab.vastdata.com:5000/vast-builder:latest
pack build sergio-exr-inspector:latest \
  --builder "docker.selab.vastdata.com:5000/vast-builder:latest" \
  --path functions/exr_inspector \
  --trust-builder --env "APP_HANDLER=main.py"

# 5. Tag and push to registry
docker tag sergio-exr-inspector:latest \
  docker.selab.vastdata.com:5000/sergio.soto/exr-inspector:latest
docker push docker.selab.vastdata.com:5000/sergio.soto/exr-inspector:latest
```

> **Note**: The `vastde functions build` command has a known Docker API version
> bug in v5.4.x dev builds. Use `pack` directly as shown above.
> See [docs/DEPLOY.md](./docs/DEPLOY.md) for full details and troubleshooting.

---

## Installation & Deployment

### Build & Deploy

The function image is built using [Cloud Native Buildpacks](https://buildpacks.io/) with the VAST builder image. Two options:

**Option A — `vastde` CLI** (may fail on Docker Desktop 4.34+, see [Known Issues](./docs/DEPLOY.md#known-issues)):

```bash
vastde functions build exr-inspector \
  -t ~/dataengine/exr_inspector/functions/exr_inspector \
  -T sergio-exr-inspector
```

**Option B — `pack` CLI** (recommended workaround):

```bash
brew install buildpacks/tap/pack
docker pull docker.selab.vastdata.com:5000/vast-builder:latest

pack build sergio-exr-inspector:latest \
  --builder "docker.selab.vastdata.com:5000/vast-builder:latest" \
  --path functions/exr_inspector \
  --trust-builder --env "APP_HANDLER=main.py"
```

Then tag and push:

```bash
docker tag sergio-exr-inspector:latest \
  docker.selab.vastdata.com:5000/sergio.soto/exr-inspector:latest
docker push docker.selab.vastdata.com:5000/sergio.soto/exr-inspector:latest
```

For step-by-step guides:
- **[docs/DEPLOY.md](./docs/DEPLOY.md)** — Canonical deployment guide
- **[docs/PROD_RUNBOOK.md](./docs/PROD_RUNBOOK.md)** — 5-phase production deployment
- **[docs/QUICK_START_VAST.md](./docs/QUICK_START_VAST.md)** — 60-75 minute walkthrough
- **[docs/TROUBLESHOOTING.md](./docs/TROUBLESHOOTING.md)** — 30+ common issues and solutions

---

## Features

- **Complete Header Metadata Extraction** — Lossless parsing of all EXR attributes, color spaces, and channel definitions
- **Multipart & Deep EXR Support** — Robust navigation through complex EXR structures via OpenImageIO
- **Type-Safe Serialization** — Handles exotic OIIO types (vectors, matrices, boxes, binary blobs) to JSON
- **Streaming-Ready Architecture** — Never loads full pixel data; reads headers only
- **Event-Driven Serverless** — Runs on VAST DataEngine with zero infrastructure management
- **VAST DataBase Persistence** — Transactional writes with idempotent upserts via the `vastdb` Python SDK
- **Vector Embeddings** — 384D metadata vectors and 128D channel fingerprints for AI/ML workflows
- **Comprehensive Testing** — 45+ unit tests with full coverage

### Planned (v1.1+)

- Pixel Statistics — Streaming per-channel min/max/mean/stddev/NaN/Inf counts
- Validation Engine — Policy-driven structural and metadata validation
- Deep EXR Analytics — Sample-level analysis for deep EXRs

---

## Configuration

### Environment Variables

```bash
VAST_DB_ENDPOINT=https://your-vast-instance.example.com
VAST_DB_ACCESS_KEY=<your-api-key>
VAST_DB_SECRET_KEY=<your-secret-key>
VAST_DB_BUCKET=exr-data        # Optional; defaults to 'exr-data'
VAST_DB_SCHEMA=exr_metadata    # Optional; defaults to 'exr_metadata'
```

### Event Payload Options

```python
InspectorConfig:
  enable_meta: bool = True          # Extract metadata (default enabled)
  enable_stats: bool = False        # Pixel statistics (v1.1)
  enable_validate: bool = False     # Validation rules (v1.2)
  schema_version: int = 1           # Output schema version
```

---

## Project Structure

```
git/
├── README.md                                # This file
├── deploy.sh                                # Automated deployment script
├── .env.example                             # Configuration template
├── docs/
│   ├── DEV_RUNBOOK.md                       # Local development guide
│   ├── PROD_RUNBOOK.md                      # Production deployment guide
│   ├── QUICK_START_VAST.md                  # Step-by-step deployment
│   ├── TROUBLESHOOTING.md                   # 30+ common issues
│   ├── VECTOR_STRATEGY.md                   # Vector embedding algorithms
│   ├── VAST_ANALYTICS_QUERIES.md            # SQL query examples
│   └── ...
└── functions/
    └── exr_inspector/
        ├── main.py                          # Primary handler
        ├── vast_db_persistence.py           # VAST DataBase persistence module
        ├── test_vast_db_persistence.py      # Comprehensive tests (45+)
        ├── requirements.txt                 # Python dependencies
        └── Aptfile                          # System library dependencies
```

---

## VAST DataBase Integration

exr-inspector persists extracted metadata to **VAST DataBase** using the `vastdb` Python SDK with transactional context managers:

```python
session = vastdb.connect(endpoint=..., access=..., secret=...)
with session.transaction() as tx:
    table = tx.bucket("exr-data").schema("exr_metadata").table("files")
    table.insert(arrow_table)
```

### Database Schema

| Table | Purpose |
|-------|---------|
| **files** | Root records with file path, size, mtime, and 384D metadata embeddings |
| **parts** | Multipart EXR structures (index, name, dimensions, tile info, compression) |
| **channels** | Channel definitions (name, type, sampling rates) with 128D fingerprints |
| **attributes** | Key-value EXR attributes with type information |

See **[VECTOR_STRATEGY.md](./docs/VECTOR_STRATEGY.md)** for schema details and **[VAST_ANALYTICS_QUERIES.md](./docs/VAST_ANALYTICS_QUERIES.md)** for query examples.

---

## Development

### Local Testing

```bash
# Set up virtual environment
python3 -m venv .venv && source .venv/bin/activate
pip install -r functions/exr_inspector/requirements.txt

# Run all tests (no VAST cluster needed)
pytest functions/exr_inspector/test_vast_db_persistence.py -v
```

See **[docs/DEV_RUNBOOK.md](./docs/DEV_RUNBOOK.md)** for the full local development workflow.

---

## Architecture

```
EXR File → OpenImageIO Reader → Header/Attributes/Channels → Schema Normalizer → JSON Output + DB Write
```

- **Stateless handler** receives events from VAST DataEngine triggers
- **Streaming**: never loads full pixel data — headers only
- **Defensive**: graceful error handling, returns errors in JSON, never crashes
- **Type-safe serialization**: handles all OIIO types (binary blobs, vectors, matrices, boxes)

---

## Status / Open Items

- **Current Version**: v0.9.0 (Release Candidate)
- **Production Ready**: Yes (with known feature limitations documented)

Open items for v1.1+:
1. Pixel Statistics (streaming per-channel analysis)
2. Validation Engine (policy-driven rules)
3. Deep EXR Handling (sample-level analytics)
4. Policy DSL (YAML vs JSON format)
5. Advanced Analytics (EXR diffing, hashing)

---

## License

See repository for licensing information.
