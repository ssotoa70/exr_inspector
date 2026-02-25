# exr-inspector Deployment Guide

Complete guide for building, pushing, and deploying exr-inspector to VAST DataEngine.

**This document supersedes**: `deployment-checklist.md`, `QUICK_START_VAST.md`, and the deployment sections of `SERVERLESS_INTEGRATION.md`. Those files are retained for reference only.

---

## Prerequisites

### Required Tools

| Tool | Version | Purpose |
|------|---------|---------|
| `vastde` | Latest | VAST DataEngine CLI (build, test, invoke) |
| `docker` | Latest | Container image build and registry push |
| `python3` | 3.10+ | Local testing and schema creation |

Verify:

```bash
vastde --version
docker --version
python3 --version
```

If `vastde` is not installed, download it from VAST support and initialize:

```bash
vastde config init \
  --password PASSWORD \
  --tenant TENANT_NAME \
  --username USERNAME \
  --builder_image_url vastdataorg/vast-builder:TAG \
  --vms_url https://VMS_IP
```

Builder image tags are listed at https://hub.docker.com/r/vastdataorg/vast-builder/

### Required Access

- VAST cluster with DataEngine enabled (v5.0.0-sp10+)
- Container registry connected to the VAST tenant (Docker Hub, ECR, Harbor, etc.)
- VAST DataBase credentials (S3-style access key + secret key)
- Network access to the VAST cluster and DataBase endpoint

### Collect Configuration

Before starting, gather these values:

```
VAST cluster URL:         ______________________________
VAST tenant name:         ______________________________
Container registry:       ______________________________  (e.g. docker.io/my-org)
Registry credentials:     ______________________________
VAST DB endpoint:         ______________________________  (e.g. s3.region.vastdata.com)
VAST DB access key:       ______________________________
VAST DB secret key:       ______________________________
S3 bucket (EXR source):   ______________________________  (e.g. exr-input-data)
```

---

## Step 1: Build the Container Image

### 1a. Initialize the function scaffold (first time only)

```bash
mkdir -p ~/functions
vastde functions init python-pip exr_inspector -t ~/functions/
```

This creates:

```
~/functions/exr_inspector/
├── Aptfile              # System package declarations (empty)
├── README.md
├── customDeps/          # Custom Python libraries (empty)
├── main.py              # Handler entry point (empty)
└── requirements.txt     # Python pip dependencies (empty)
```

### 1b. Copy the exr-inspector source files

Copy the repo source into the scaffold, overwriting the empty files:

```bash
REPO=/path/to/exr-inspector/git

cp "$REPO/functions/exr_inspector/main.py"                ~/functions/exr_inspector/
cp "$REPO/functions/exr_inspector/vast_db_persistence.py" ~/functions/exr_inspector/
cp "$REPO/functions/exr_inspector/requirements.txt"       ~/functions/exr_inspector/
cp "$REPO/functions/exr_inspector/Aptfile"                ~/functions/exr_inspector/
```

Verify contents:

```bash
cat ~/functions/exr_inspector/requirements.txt
# Should show: pyarrow>=10.0.0 and vastdb>=1.3.9

cat ~/functions/exr_inspector/Aptfile
# Should show: libopenimageio-dev and libopenexr-dev
```

**What each file does:**

| File | Purpose |
|------|---------|
| `main.py` | DataEngine handler. Exports `init(ctx)` and `handler(ctx, event)`. |
| `vast_db_persistence.py` | VAST DataBase persistence with vector embeddings. |
| `requirements.txt` | Python pip dependencies (`pyarrow`, `vastdb`). |
| `Aptfile` | Debian system packages installed during image build (`libopenimageio-dev`, `libopenexr-dev`). OpenImageIO Python bindings come from this package. |

### 1c. Handler signature requirement

The `vastde` CLI validates that `main.py` contains `init(ctx)` and `handler(ctx, event)` with **exact** signatures. Type annotations cause validation to fail:

```python
# WRONG — vastde rejects this:
def init(ctx: Any) -> None:

# CORRECT — plain signatures:
def init(ctx):
def handler(ctx, event):
```

### 1d. Build the image

The `vastde` CLI flags use short forms: `-t` (target directory), `-T` (image tag).

```bash
FUNC_NAME="exr-inspector"
FUNC_TAG="sergio-exr-inspector"
FUNC_PATH="$HOME/dataengine/exr_inspector/functions/exr_inspector"

vastde functions build $FUNC_NAME -t $FUNC_PATH -T $FUNC_TAG
```

The `vastde` CLI will:
1. Create a Docker image using the VAST builder base image
2. Install system packages from `Aptfile` via `apt-get`
3. Install Python packages from `requirements.txt` via `pip`
4. Package `main.py` and all other files as the function payload

**Known issue — `vastde` v5.4.x Docker API mismatch**: The `vastde` dev builds
(v5.4.1-dev and similar) use Docker API version 1.38, which is rejected by
Docker Desktop 4.34+ (minimum API 1.44). The error looks like:

```
error building app: failed to fetch builder image '...': client version 1.38 is too old.
Minimum supported API version is 1.44
```

**Workaround — build with `pack` directly** (same buildpack tool `vastde` uses):

```bash
# Install pack CLI (one time)
brew install buildpacks/tap/pack

# Pull the builder image manually first
docker pull docker.selab.vastdata.com:5000/vast-builder:latest

# Build using pack (bypasses the vastde API version bug)
pack build sergio-exr-inspector:latest \
  --builder "docker.selab.vastdata.com:5000/vast-builder:latest" \
  --path "$FUNC_PATH" \
  --trust-builder \
  --env "APP_HANDLER=main.py"
```

**Note on Docker Desktop containerd**: If Docker Desktop has "Use containerd for
pulling and storing images" enabled (Settings > General), `pack` may fail at the
final export step with `failed to fetch base layers: no such file or directory`.
Temporarily disable containerd in Docker Desktop settings, rebuild, then
re-enable it.

Verify the image was built:

```bash
docker images | grep exr-inspector
# sergio-exr-inspector    latest    <hash>    <date>    <size>
```

### 1e. Test locally (optional but recommended)

Start the function container locally:

```bash
vastde functions localrun
```

In a second terminal, invoke it with a test event:

```bash
vastde functions invoke
```

This sends a default cloud event to the running container. Without a real EXR file, you will see an error about a missing file path, which confirms the handler is running correctly.

---

## Step 2: Push to Container Registry

### 2a. Tag the image for your registry

```bash
# Format: docker tag <local-image> <registry>/<repository>:<tag>

# Docker Hub example:
docker tag exr-inspector:latest docker.io/my-org/exr-inspector:v0.9.0

# AWS ECR example:
docker tag exr-inspector:latest 123456789.dkr.ecr.us-east-1.amazonaws.com/exr-inspector:v0.9.0

# Private registry example:
docker tag exr-inspector:latest registry.internal:5000/exr-inspector:v0.9.0
```

### 2b. Authenticate with the registry

```bash
# Docker Hub:
docker login -u <username>

# AWS ECR:
aws ecr get-login-password --region us-east-1 | \
  docker login --username AWS --password-stdin 123456789.dkr.ecr.us-east-1.amazonaws.com

# Private registry:
docker login registry.internal:5000
```

### 2c. Push the image

```bash
docker push docker.io/my-org/exr-inspector:v0.9.0
```

Verify:

```bash
# Pull it back to confirm the push succeeded:
docker pull docker.io/my-org/exr-inspector:v0.9.0
```

**Important**: The container registry must have a connection configured on the VAST tenant. This is an admin-level setting in the VAST UI. If you cannot see your pushed image from within VAST, ask your cluster admin to add the registry connection.

---

## Step 3: Create the VAST DataBase Schema

The function persists EXR metadata into four tables. Create these before deploying the pipeline.

### 3a. Install SDK locally

```bash
pip install vastdb pyarrow
```

### 3b. Set credentials

```bash
export VAST_DB_ENDPOINT="http://s3.region.vastdata.com"
export VAST_DB_ACCESS_KEY="<your-access-key>"
export VAST_DB_SECRET_KEY="<your-secret-key>"
```

### 3c. Create schema and tables

```python
#!/usr/bin/env python3
"""Create VAST DataBase schema for exr-inspector."""

import os
import vastdb
import pyarrow as pa

endpoint = os.environ["VAST_DB_ENDPOINT"]
access_key = os.environ["VAST_DB_ACCESS_KEY"]
secret_key = os.environ["VAST_DB_SECRET_KEY"]

session = vastdb.connect(
    endpoint=endpoint,
    access=access_key,
    secret=secret_key,
)

BUCKET = "exr-metadata"       # Change to match your bucket
SCHEMA = "exr_metadata"       # Schema name

with session.transaction() as tx:
    bucket = tx.bucket(BUCKET)
    schema = bucket.create_schema(SCHEMA)

    # 1. files table
    schema.create_table("files", pa.schema([
        ("file_id", pa.string()),
        ("file_path", pa.string()),
        ("file_path_normalized", pa.string()),
        ("header_hash", pa.string()),
        ("size_bytes", pa.int64()),
        ("mtime", pa.string()),
        ("multipart_count", pa.int32()),
        ("is_deep", pa.bool_()),
        ("metadata_embedding", pa.list_(pa.float32(), 384)),
        ("inspection_timestamp", pa.string()),
        ("inspection_count", pa.int32()),
        ("last_inspected", pa.string()),
    ]))
    print("  created: files")

    # 2. parts table
    schema.create_table("parts", pa.schema([
        ("file_id", pa.string()),
        ("file_path", pa.string()),
        ("part_index", pa.int32()),
        ("part_name", pa.string()),
        ("view_name", pa.string()),
        ("multi_view", pa.bool_()),
        ("data_window", pa.string()),
        ("display_window", pa.string()),
        ("pixel_aspect_ratio", pa.float32()),
        ("line_order", pa.string()),
        ("compression", pa.string()),
        ("is_tiled", pa.bool_()),
        ("tile_width", pa.int32()),
        ("tile_height", pa.int32()),
        ("tile_depth", pa.int32()),
        ("is_deep", pa.bool_()),
    ]))
    print("  created: parts")

    # 3. channels table
    schema.create_table("channels", pa.schema([
        ("file_id", pa.string()),
        ("file_path", pa.string()),
        ("part_index", pa.int32()),
        ("channel_name", pa.string()),
        ("channel_type", pa.string()),
        ("x_sampling", pa.int32()),
        ("y_sampling", pa.int32()),
        ("channel_fingerprint", pa.list_(pa.float32(), 128)),
    ]))
    print("  created: channels")

    # 4. attributes table
    schema.create_table("attributes", pa.schema([
        ("file_id", pa.string()),
        ("file_path", pa.string()),
        ("part_index", pa.int32()),
        ("attribute_name", pa.string()),
        ("attribute_type", pa.string()),
        ("attribute_value", pa.string()),
    ]))
    print("  created: attributes")

print(f"\nSchema '{SCHEMA}' ready with 4 tables.")
```

Save this as `create_schema.py` and run:

```bash
python3 create_schema.py
```

### 3d. Verify

```python
with session.transaction() as tx:
    schema = tx.bucket(BUCKET).schema(SCHEMA)
    for name in ["files", "parts", "channels", "attributes"]:
        table = schema.table(name)
        print(f"  {name}: {len(table.schema.names)} columns")
```

---

## Step 4: Create Function in VAST DataEngine UI

1. Log in to the VAST DataEngine web UI.
2. Navigate to **Manage Elements > Functions**.
3. Click **Create New Function**.
4. Fill in:

| Field | Value |
|-------|-------|
| **Name** | `exr-inspector` |
| **Description** | `EXR file metadata extraction and VAST DataBase persistence` |
| **Revision Alias** | `v0.9.0` |
| **Container Registry** | Your registry (e.g. `docker.io`) |
| **Artifact Source** | Your repository path (e.g. `my-org/exr-inspector`) |
| **Image Tag** | `v0.9.0` |

5. Click **Create Function**.

VAST will validate registry access and pull the image.

---

## Step 5: Create Pipeline and Trigger

### 5a. Create a Trigger

1. Navigate to **Manage Elements > Triggers**.
2. Click **Create New Trigger**.
3. Configure:

| Setting | Value |
|---------|-------|
| **Trigger Name** | `exr-upload-trigger` |
| **Trigger Type** | `Element` |
| **Source View** | Select the view containing your EXR files |
| **Event Type** | `ElementCreated` |
| **Suffix Filter** | `.exr` |
| **Prefix Filter** | *(optional, e.g. `/renders/`)* |

### 5b. Create a Pipeline

1. Navigate to **Pipeline Management**.
2. Click **Create New Pipeline**.
3. Name: `exr-inspect-pipeline`, Description: `Inspect EXR files on upload`.
4. In the **Visual Builder**:
   - Drag the `exr-upload-trigger` from the trigger library onto the canvas.
   - Drag the `exr-inspector` function onto the canvas.
   - Connect the trigger output handle to the function input handle.

### 5c. Configure Function Deployment

Click the `exr-inspector` function node in the Visual Builder to configure:

**Environment Variables** (required for VAST DataBase persistence):

| Variable | Value |
|----------|-------|
| `VAST_DB_ENDPOINT` | `http://s3.region.vastdata.com` |
| `VAST_DB_ACCESS_KEY` | Your access key |
| `VAST_DB_SECRET_KEY` | Your secret key |
| `VAST_DB_BUCKET` | `exr-data` (or your bucket name) |
| `VAST_DB_SCHEMA` | `exr_metadata` |

**Resources** (recommended starting values):

| Setting | Value |
|---------|-------|
| **Timeout** | `300` seconds |
| **Log Level** | `INFO` |
| **Method of Delivery** | `unordered` (concurrent) |
| **Min Concurrency** | `1` |
| **Max Concurrency** | `10` |
| **Memory** | `1024` MB |

For sensitive credentials, use **Secret Keys** instead of environment variables. Secrets are accessible in function code via `ctx.secrets` from the VAST DataEngine Runtime SDK.

### 5d. Deploy

Click **Deploy Pipeline**. VAST DataEngine will provision the function containers and activate the trigger.

---

## Step 6: Verify

### Upload a test EXR file

Place an EXR file in the source view that the trigger is watching. The pipeline should invoke the function automatically.

### Check logs

```bash
vastde pipelines logs exr-inspect-pipeline --tail 50
```

Or in the VAST UI: **Pipeline Management > exr-inspect-pipeline > Logs**.

Expected log output:

```
[INFO] Processing: /renders/test_shot.exr
[INFO] Extracted: 8 channels, 2 parts, 34 attributes
[INFO] VAST DataBase session created: s3.region.vastdata.com
[INFO] File inserted: a1b2c3d4e5f6
```

### Query the database

```python
import vastdb

session = vastdb.connect(endpoint=..., access=..., secret=...)

with session.transaction() as tx:
    files = tx.bucket("exr-metadata").schema("exr_metadata").table("files")
    # Select recent inspections
    results = files.select()
    print(f"Total files inspected: {results.num_rows}")
```

---

## Known Issues

### vastde v5.4.x Docker API mismatch

The `vastde` dev builds (v5.4.1-dev) ship with an embedded Docker client that
negotiates API version 1.38. Docker Desktop 4.34+ requires minimum API 1.44.
The `DOCKER_API_VERSION` env var does **not** help because `vastde` ignores it.

**Workaround**: Use `pack` CLI directly (see Step 1d above). This is the same
Cloud Native Buildpacks tool that `vastde` wraps internally.

### vastde handler signature validation

The `vastde` CLI performs naive text matching for `def init(ctx)` and
`def handler(ctx, event)`. Adding type annotations (e.g. `ctx: Any`) causes
validation to fail even though the functions exist. Remove annotations from
`init()` and `handler()` signatures before building.

### Docker Desktop containerd image store

Docker Desktop with the containerd image store enabled can cause `pack build`
to fail at the export step. Temporarily disable containerd (Docker Desktop >
Settings > General > uncheck "Use containerd for pulling and storing images")
for the build, then re-enable it.

---

## Troubleshooting

### Build fails: "Docker not running"

```bash
docker ps  # Verify Docker daemon is running
```

### Build fails: "System dependency not found"

Ensure `Aptfile` contains:

```
libopenimageio-dev
libopenexr-dev
```

### Push fails: "Authentication required"

```bash
docker login <registry-url>
```

Ensure the registry has a connection configured on the VAST tenant (admin setting).

### Function invoked but no database writes

1. Check environment variables are set on the function deployment (not just the pipeline level).
2. Verify the VAST DataBase endpoint is reachable from the function container.
3. Check function logs for `"VAST persistence skipped"` — this means credentials are missing.
4. Check for `"vastdb SDK not available"` — this means the `vastdb` package is not installed in the container.

### Trigger not firing

1. Verify the trigger event type matches: `ElementCreated`.
2. Check the suffix filter is `.exr` (case-sensitive).
3. Confirm the source view is correct and the file was actually created (not just modified).
4. Check trigger status in **Manage Elements > Triggers**.

### Schema not found

Re-run the `create_schema.py` script from Step 3. Verify the bucket name and schema name match what is set in `VAST_DB_SCHEMA`.

---

## Quick Reference: Full Command Sequence

```bash
# 1. Scaffold (first time only)
vastde functions init python-pip exr_inspector -t ~/dataengine/

# 2. Copy source files
REPO=/path/to/exr-inspector/git
cp "$REPO"/functions/exr_inspector/{main.py,vast_db_persistence.py,requirements.txt,Aptfile} \
   ~/dataengine/exr_inspector/

# 3. Build (option A: vastde — may fail on Docker Desktop, see Known Issues)
vastde functions build exr-inspector \
  -t ~/dataengine/exr_inspector/functions/exr_inspector \
  -T sergio-exr-inspector

# 3. Build (option B: pack — workaround for vastde Docker API bug)
brew install buildpacks/tap/pack                                    # one time
docker pull docker.selab.vastdata.com:5000/vast-builder:latest      # one time
pack build sergio-exr-inspector:latest \
  --builder "docker.selab.vastdata.com:5000/vast-builder:latest" \
  --path ~/dataengine/exr_inspector/functions/exr_inspector \
  --trust-builder \
  --env "APP_HANDLER=main.py"

# 4. Test locally
vastde functions localrun   # terminal 1
vastde functions invoke     # terminal 2

# 5. Tag and push
docker tag sergio-exr-inspector:latest \
  docker.selab.vastdata.com:5000/sergio.soto/exr-inspector:latest
docker push docker.selab.vastdata.com:5000/sergio.soto/exr-inspector:latest

# 6. Create schema (see Step 3 script)
python3 create_schema.py

# 7. VAST UI: Create function, trigger, pipeline, deploy
```
