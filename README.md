# exr-inspector

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://github.com/ssotoa70/exr_inspector/blob/main/LICENSE)
[![Python](https://img.shields.io/badge/python-3.12-green.svg)](https://www.python.org/downloads/)
[![VAST DataEngine](https://img.shields.io/badge/VAST-DataEngine-blue.svg)](https://www.vastdata.com/)

**Serverless EXR metadata extraction for VAST DataEngine.**

exr-inspector is a VAST DataEngine function that automatically extracts metadata, channels (AOVs), and header attributes from OpenEXR files as they are ingested into a VAST S3 bucket. Results are persisted to VAST DataBase with deterministic vector embeddings for similarity search.

---

## How It Works

```
EXR file uploaded to S3 bucket
  --> VAST DataEngine ElementCreated trigger (.exr suffix filter)
    --> exr-inspector function container
      --> Downloads EXR via boto3 from VAST S3
      --> Parses headers with OpenImageIO (no pixel data read)
      --> Computes deterministic vector embeddings
      --> Persists to 4 VAST DataBase tables (auto-created)
      --> Returns structured JSON result
```

## What It Extracts

| Scope | Fields |
|-------|--------|
| **File** | Part count, deep flag, file size, modification time |
| **Parts** | Width, height, compression, tiling, data/display windows, pixel aspect ratio, line order |
| **Channels** | Name (AOV layer), type (HALF/FLOAT/UINT), x/y sampling rates |
| **Attributes** | All EXR header attributes: chromaticities, color space, owner, software, frame rate, timecode, camera matrices, etc. |

## Project Structure

```
functions/exr_inspector/
  main.py                  # DataEngine handler (init + handler)
  vast_db_persistence.py   # VAST DataBase persistence + auto-provisioning
  requirements.txt         # Python dependencies (boto3, pyarrow, vastdb)
  Aptfile                  # System packages (libopenimageio-dev, libopenexr-dev)
Dockerfile.fix             # LD_LIBRARY_PATH fix for CNB buildpack images
deploy.sh                  # Automated deployment script
docs/
  DEPLOYMENT.md            # Build, deploy, and configure guide
  DATABASE_SCHEMA.md       # Table schemas, Trino queries, vector search
  ARCHITECTURE.md          # Handler flow, event model, design decisions
  CONFIGURATION.md         # Environment variables reference
  TROUBLESHOOTING.md       # Common issues and solutions
```

## Quick Start

```bash
# Clone
git clone https://github.com/ssotoa70/exr_inspector.git
cd exr_inspector

# Install dependencies (local development)
pip install -r functions/exr_inspector/requirements.txt

# Run tests (no VAST cluster required)
pytest functions/exr_inspector/test_vast_db_persistence.py -v

# Build container image
vastde functions build exr-inspector --target functions/exr_inspector --pull-policy never

# See docs/DEPLOYMENT.md for full deployment guide
```

## Documentation

| Document | Description |
|----------|-------------|
| [Deployment Guide](docs/DEPLOYMENT.md) | Build, push, create function, configure pipeline |
| [Database Schema](docs/DATABASE_SCHEMA.md) | Table definitions, Trino queries, vector search |
| [Architecture](docs/ARCHITECTURE.md) | Event flow, handler design, persistence patterns |
| [Configuration](docs/CONFIGURATION.md) | Environment variables and secrets reference |
| [Troubleshooting](docs/TROUBLESHOOTING.md) | Common issues and solutions |

## Requirements

- **VAST Cluster** 5.4+ with DataEngine enabled
- **vastde CLI** v5.4.1+
- **Docker** with `min-api-version: "1.38"` (see [Troubleshooting](docs/TROUBLESHOOTING.md))
- **Python** 3.12 (container runtime)
- **S3 bucket** with DataEngine element trigger configured

## License

[MIT](LICENSE)
