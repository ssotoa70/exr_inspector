# exr-inspector: Quick-Start Guide for VAST DataEngine Integration

**Complete deployment and integration guide for exr-inspector with VAST DataEngine and VAST DataBase.**

This guide walks you through deploying the exr-inspector serverless function to VAST DataEngine and configuring persistent metadata storage in VAST DataBase. Estimated total time: 60-75 minutes.

---

## Table of Contents

1. [Prerequisites (5 min)](#prerequisites)
2. [Step 1: Create VAST Database Schema (10 min)](#step-1-create-vast-database-schema)
3. [Step 2: Build & Deploy Function (15 min)](#step-2-build--deploy-function)
4. [Step 3: Configure Credentials (5 min)](#step-3-configure-credentials)
5. [Step 4: Create S3 Trigger (10 min)](#step-4-create-s3-trigger)
6. [Step 5: Query Results (15 min)](#step-5-query-results)
7. [Troubleshooting](#troubleshooting)
8. [Next Steps](#next-steps)

---

## Prerequisites

**Estimated Time: 5 minutes**

Before you begin, ensure you have:

### System Requirements

- **VAST Cluster**: v5.0.0-sp10 or later (DataEngine + DataBase)
- **Python**: 3.10+ (for local testing)
- **Docker**: Latest version (for building container images)
- **VAST DataEngine CLI**: `vastde` command-line tool installed and configured

Verify your tools:
```bash
# Check VAST DataEngine CLI
vastde --version

# Check Docker
docker --version

# Check Python
python3 --version
```

### VAST Configuration

You need:

1. **VAST Cluster Access**
   - Admin or operator credentials for VAST UI
   - Network access to cluster (IP address or hostname)

2. **Container Registry**
   - Registry connected to VAST tenant (Docker Hub, ECR, Harbor, etc.)
   - Push credentials (username, password, or service account)
   - Example: `docker.io/your-org` or `ecr.aws.com/your-account`

3. **S3/Object Storage**
   - S3-compatible bucket for input EXR files (VAST DataEngine trigger source)
   - S3 credentials (access key, secret key) or IAM role
   - Example: bucket name `exr-input-data`

4. **VAST DataBase Endpoint**
   - S3 endpoint URL for VAST DataBase (usually: `s3.region.vastdata.com`)
   - DataBase access credentials (access key, secret key)
   - Sufficient quota for new schema and tables

### Prepare Your Environment

Collect and note the following information (you'll need it later):

```
Container Registry:     [ ]  docker.io/my-org
Registry Username:      [ ]  _______________________
Registry Password:      [ ]  (securely stored)
VAST Cluster URL:       [ ]  https://vast-cluster.internal
VAST CLI Config:        [ ]  ~/.vastde/config
S3 Bucket (input):      [ ]  exr-input-data
S3 Credentials:         [ ]  Access key and secret key
VAST DB Endpoint:       [ ]  s3.region.vastdata.com
VAST DB Credentials:    [ ]  Access key and secret key
```

### Optional: Install Dependencies Locally

For local testing and development (skip if deploying directly):

```bash
# Clone/navigate to exr-inspector repository
cd /path/to/exr-inspector

# Install Python dependencies
pip install -r functions/exr_inspector/requirements.txt

# Install system libraries (macOS)
brew install openimageio openexr

# Or on Ubuntu/Debian
sudo apt-get install -y libopenimageio-dev libopenexr-dev
```

---

## Step 1: Create VAST Database Schema

**Estimated Time: 10 minutes**

The exr-inspector function stores metadata in VAST DataBase using a normalized relational schema. You must create the tables before the function can persist data.

### Option A: Using the Python SDK (Recommended)

This approach uses the VAST DataBase Python SDK to create schema and tables programmatically.

**1. Create schema initialization script:**

```bash
cd /tmp
cat > create_exr_schema.py << 'EOF'
"""
Create VAST DataBase schema for exr-inspector metadata persistence.
Requires: vastdb-sdk, pyarrow
"""

import os
import pyarrow as pa
from vastdb import VastdbConnector

# Configuration from environment
endpoint = os.getenv("VAST_DB_ENDPOINT")
access_key = os.getenv("VAST_DB_ACCESS_KEY")
secret_key = os.getenv("VAST_DB_SECRET_KEY")
region = os.getenv("VAST_DB_REGION", "us-east-1")
schema_name = os.getenv("VAST_DB_SCHEMA", "exr_metadata")

if not all([endpoint, access_key, secret_key]):
    raise ValueError("Missing VAST_DB_* environment variables")

print(f"Connecting to VAST DataBase: {endpoint}")
connector = VastdbConnector(
    endpoint=endpoint,
    access_key_id=access_key,
    secret_access_key=secret_key,
    region=region,
    use_ssl=True,
)

bucket = connector.get_bucket("exr-metadata-prod")
print(f"Using bucket: exr-metadata-prod")

# Create schema namespace
schema = bucket.create_schema(schema_name)
print(f"Created schema: {schema_name}")

# Define table schemas using PyArrow
files_schema = pa.schema([
    ("file_id", pa.string()),  # Primary key
    ("file_path", pa.string()),
    ("file_path_normalized", pa.string()),  # Unique with header_hash
    ("header_hash", pa.string()),  # Unique with file_path_normalized
    ("size_bytes", pa.int64()),
    ("mtime", pa.string()),  # ISO8601 timestamp
    ("multipart_count", pa.int32()),
    ("is_deep", pa.bool_()),
    ("metadata_embedding", pa.list_(pa.float32(), 384)),  # 384-dim vector
    ("inspection_timestamp", pa.string()),  # ISO8601 timestamp
    ("inspection_count", pa.int32()),
    ("last_inspected", pa.string()),  # ISO8601 timestamp
])

parts_schema = pa.schema([
    ("file_id", pa.string()),  # Foreign key
    ("file_path", pa.string()),
    ("part_index", pa.int32()),
    ("part_name", pa.string()),
    ("view_name", pa.string()),
    ("multi_view", pa.bool_()),
    ("data_window", pa.string()),  # JSON
    ("display_window", pa.string()),  # JSON
    ("pixel_aspect_ratio", pa.float32()),
    ("line_order", pa.string()),
    ("compression", pa.string()),
    ("is_tiled", pa.bool_()),
    ("tile_width", pa.int32()),
    ("tile_height", pa.int32()),
    ("is_deep", pa.bool_()),
])

channels_schema = pa.schema([
    ("file_id", pa.string()),  # Foreign key
    ("file_path", pa.string()),
    ("part_index", pa.int32()),
    ("channel_name", pa.string()),
    ("channel_type", pa.string()),
    ("x_sampling", pa.int32()),
    ("y_sampling", pa.int32()),
    ("channel_fingerprint", pa.list_(pa.float32(), 128)),  # 128-dim vector
])

attributes_schema = pa.schema([
    ("file_id", pa.string()),  # Foreign key
    ("file_path", pa.string()),
    ("part_index", pa.int32()),
    ("attribute_name", pa.string()),
    ("attribute_type", pa.string()),
    ("attribute_value", pa.string()),  # JSON
])

# Create tables
print("Creating tables...")
schema.create_table("files", files_schema)
print("  ✓ files")
schema.create_table("parts", parts_schema)
print("  ✓ parts")
schema.create_table("channels", channels_schema)
print("  ✓ channels")
schema.create_table("attributes", attributes_schema)
print("  ✓ attributes")

print(f"\nSuccess! Schema '{schema_name}' created with 4 tables.")
print("\nTables created:")
print("  - files (file metadata and embeddings)")
print("  - parts (multipart structure)")
print("  - channels (channel definitions)")
print("  - attributes (EXR attributes)")
EOF
```

**2. Set environment variables and run:**

```bash
export VAST_DB_ENDPOINT="s3.region.vastdata.com"
export VAST_DB_ACCESS_KEY="your-access-key"
export VAST_DB_SECRET_KEY="your-secret-key"
export VAST_DB_REGION="us-east-1"
export VAST_DB_SCHEMA="exr_metadata"

pip install vastdb-sdk pyarrow
python create_exr_schema.py
```

Expected output:
```
Connecting to VAST DataBase: s3.region.vastdata.com
Using bucket: exr-metadata-prod
Created schema: exr_metadata
Creating tables...
  ✓ files
  ✓ parts
  ✓ channels
  ✓ attributes

Success! Schema 'exr_metadata' created with 4 tables.
```

### Option B: Using SQL/ADBC

If you prefer direct SQL execution, use ADBC to connect and create tables:

```python
import adbc_driver_manager
import adbc_driver_postgresql  # or your VAST DB SQL driver

uri = "s3.region.vastdata.com:443"
conn = adbc_driver_manager.get_connection(
    "vastdb",
    uri=uri,
    username="your-access-key",
    password="your-secret-key",
)

# Create schema
conn.execute("CREATE SCHEMA IF NOT EXISTS exr_metadata")

# Create files table
conn.execute("""
    CREATE TABLE exr_metadata.files (
        file_id VARCHAR PRIMARY KEY,
        file_path VARCHAR,
        file_path_normalized VARCHAR,
        header_hash VARCHAR,
        size_bytes BIGINT,
        mtime VARCHAR,
        multipart_count INTEGER,
        is_deep BOOLEAN,
        metadata_embedding FLOAT32[384],
        inspection_timestamp VARCHAR,
        inspection_count INTEGER,
        last_inspected VARCHAR,
        UNIQUE(file_path_normalized, header_hash)
    )
""")

# Create parts, channels, attributes tables similarly...
conn.commit()
```

### Verify Schema Creation

Check that tables were created successfully:

```bash
# Using Python SDK
python << 'EOF'
import os
from vastdb import VastdbConnector

connector = VastdbConnector(
    endpoint=os.getenv("VAST_DB_ENDPOINT"),
    access_key_id=os.getenv("VAST_DB_ACCESS_KEY"),
    secret_access_key=os.getenv("VAST_DB_SECRET_KEY"),
)
bucket = connector.get_bucket("exr-metadata-prod")
schema = bucket.get_schema("exr_metadata")

tables = schema.list_tables()
print(f"Tables in schema 'exr_metadata':")
for table_name in tables:
    table = schema.get_table(table_name)
    print(f"  - {table_name}: {len(table.schema.names)} columns")
EOF
```

Expected output:
```
Tables in schema 'exr_metadata':
  - files: 12 columns
  - parts: 15 columns
  - channels: 8 columns
  - attributes: 5 columns
```

---

## Step 2: Build & Deploy Function

**Estimated Time: 15 minutes**

### 2A. Build Container Image

**1. Initialize function scaffold (first time only):**

```bash
# Create functions workspace
mkdir -p ~/functions
cd ~/functions

# Initialize exr-inspector function
vastde functions init python-pip exr_inspector -t .
```

This creates:
```
~/functions/exr_inspector/
├── main.py               # Handler entry point (replace with repo version)
├── requirements.txt      # Python dependencies
├── Aptfile              # System library dependencies
├── customDeps/          # Custom dependency directory
└── README.md            # Function documentation
```

**2. Copy exr-inspector code to function directory:**

```bash
# Copy repo files (replace with actual repo path)
cp /path/to/exr-inspector/functions/exr_inspector/main.py ~/functions/exr_inspector/
cp /path/to/exr-inspector/functions/exr_inspector/vast_db_persistence.py ~/functions/exr_inspector/
cp /path/to/exr-inspector/functions/exr_inspector/requirements.txt ~/functions/exr_inspector/
cp /path/to/exr-inspector/functions/exr_inspector/Aptfile ~/functions/exr_inspector/
```

**3. Verify function requirements:**

```bash
cat ~/functions/exr_inspector/requirements.txt
```

Should contain:
```
OpenImageIO>=2.4.0
pyarrow>=10.0.0
vastdb-sdk>=1.0.0
```

**4. Build the container image:**

```bash
cd ~/functions

# Build image (tags as exr-inspector:latest)
vastde functions build exr-inspector \
  -target ./exr_inspector \
  --image-tag exr-inspector

# Progress indicator:
# [1/4] Building Docker image...
# [2/4] Installing dependencies...
# [3/4] Optimizing layers...
# [4/4] Complete
# Successfully built: exr-inspector:latest
```

Verify the build:
```bash
docker images | grep exr-inspector
```

Expected output:
```
exr-inspector          latest    abc123def456    2 minutes ago    256MB
```

### 2B. Push to Container Registry

**1. Tag the image for your registry:**

```bash
# Example: Docker Hub
docker tag exr-inspector:latest docker.io/my-org/exr-inspector:v1.0.0

# Or: AWS ECR
docker tag exr-inspector:latest 123456789.dkr.ecr.us-east-1.amazonaws.com/exr-inspector:v1.0.0

# Or: Private registry
docker tag exr-inspector:latest my-registry.internal:5000/exr-inspector:v1.0.0
```

**2. Log in to registry:**

```bash
# Docker Hub
docker login -u your-username

# AWS ECR (use IAM credentials)
aws ecr get-login-password --region us-east-1 | \
  docker login --username AWS --password-stdin 123456789.dkr.ecr.us-east-1.amazonaws.com

# Private registry
docker login my-registry.internal:5000
```

**3. Push the image:**

```bash
# Docker Hub
docker push docker.io/my-org/exr-inspector:v1.0.0

# AWS ECR
docker push 123456789.dkr.ecr.us-east-1.amazonaws.com/exr-inspector:v1.0.0

# Private registry
docker push my-registry.internal:5000/exr-inspector:v1.0.0
```

Verify push:
```bash
docker images exr-inspector
```

### 2C. Create Function in VAST UI

**1. Navigate to Functions management:**
   - Log in to VAST DataEngine UI
   - Go to **Manage Elements → Functions**

**2. Click "Create New Function"**

**3. Fill in function details:**

| Field | Value |
|-------|-------|
| **Name** | `exr-inspector` |
| **Description** | `EXR file metadata extraction and validation` |
| **Revision Alias** | `v1.0.0` |
| **Revision Description** | `Initial release with VAST DataBase persistence` |
| **Container Registry** | `docker.io` (or your registry host) |
| **Artifact Source** | `my-org/exr-inspector` (your registry path) |
| **Image Tag** | `v1.0.0` (must match your tag) |
| **Full Image Path** | (auto-generated) `docker.io/my-org/exr-inspector:v1.0.0` |

**4. Click "Create Function"**

VAST DataEngine will:
- Validate registry access
- Pull and cache the container image
- Make the function available for pipelines

Expected confirmation:
```
Function 'exr-inspector' created successfully
Version: v1.0.0 (alias)
Status: Ready
```

---

## Step 3: Configure Credentials

**Estimated Time: 5 minutes**

The exr-inspector function needs credentials to:
1. Read input EXR files from S3
2. Write metadata to VAST DataBase

### 3A. Set Environment Variables

These variables are passed to the function container at runtime.

**In VAST DataEngine UI:**

1. Navigate to **Manage Elements → Functions → exr-inspector**
2. Click **Edit Environment Variables**
3. Add the following variables:

```
VAST_DB_ENDPOINT=s3.region.vastdata.com
VAST_DB_ACCESS_KEY=<your-access-key>
VAST_DB_SECRET_KEY=<your-secret-key>
VAST_DB_REGION=us-east-1
VAST_DB_SCHEMA=exr_metadata
```

**Or, via VAST CLI:**

```bash
vastde functions set-env exr-inspector \
  --env VAST_DB_ENDPOINT=s3.region.vastdata.com \
  --env VAST_DB_ACCESS_KEY=<key> \
  --env VAST_DB_SECRET_KEY=<secret> \
  --env VAST_DB_REGION=us-east-1 \
  --env VAST_DB_SCHEMA=exr_metadata
```

### 3B. Test Connection

**Create a test event to verify connectivity:**

```bash
# Create test event file
cat > test_event.json << 'EOF'
{
  "data": {
    "path": "/data/test.exr",
    "meta": true
  }
}
EOF

# Invoke function locally for testing
vastde functions localrun --event test_event.json
```

Expected output (if successful):
```json
{
  "status": "success",
  "file": {
    "path": "/data/test.exr",
    "size_bytes": 1048576
  },
  "persistence": {
    "status": "success",
    "file_id": "abc123def456",
    "inserted": true,
    "message": "File persisted: abc123def456"
  }
}
```

If you see persistence errors:
- Check environment variables are set correctly
- Verify schema exists in VAST DataBase (Step 1)
- Check VAST_DB_ENDPOINT is reachable
- Verify access credentials

---

## Step 4: Create S3 Trigger

**Estimated Time: 10 minutes**

Event-driven triggers automatically invoke exr-inspector when new EXR files are uploaded to S3.

### 4A. Create Pipeline

**1. In VAST DataEngine UI:**
   - Go to **Pipelines**
   - Click **Create New Pipeline**

**2. Enter pipeline details:**
   - **Name**: `exr-inspect-pipeline`
   - **Description**: `Inspect EXR files on S3 upload`

**3. Add function to pipeline:**
   - Click **Add Stage**
   - Select **exr-inspector** function
   - Confirm revision (v1.0.0)

### 4B. Configure S3 Trigger

**1. Click "Add Trigger"**

**2. Select trigger type: "S3 Object Create"**

**3. Configure bucket and filters:**

| Setting | Value |
|---------|-------|
| **S3 Bucket** | `exr-input-data` |
| **Prefix** | `/renders/` (optional) |
| **Suffix** | `.exr` |
| **Events** | `s3:ObjectCreated:*` |

**4. Test configuration:**
   - Click **Verify Trigger**
   - VAST will test connectivity to S3 bucket
   - Expected: "Trigger verified successfully"

### 4C. Deploy Pipeline

**1. Click "Deploy Pipeline"**

**2. Monitor initial run:**
   - Go to **Pipeline Runs**
   - Wait for status to change from "Pending" to "Running"
   - Expected: First run processes any existing objects in bucket

**3. First run should:**
   - Read headers from all EXR files in bucket
   - Extract metadata
   - Write to VAST DataBase (if configured)
   - Produce inspection results

Check logs:
```bash
vastde pipelines logs exr-inspect-pipeline --tail 50
```

Expected log output:
```
[INFO] Starting pipeline: exr-inspect-pipeline
[INFO] Trigger: s3:ObjectCreated event on s3://exr-input-data/*.exr
[INFO] Processing: /renders/shot_001.exr (2.1 MB)
[INFO] Extracted: 8 channels, 2 parts, 42 attributes
[INFO] Persisted to VAST DataBase: file_id=abc123def456
[INFO] Processing: /renders/shot_002.exr (1.8 MB)
[INFO] Extracted: 8 channels, 2 parts, 42 attributes
[INFO] Persisted to VAST DataBase: file_id=abc123def457
[INFO] Pipeline run completed: 2 files processed
```

### 4D: Monitor First Run

**Watch the initial execution:**

```bash
# Stream real-time logs
vastde pipelines logs exr-inspect-pipeline --follow

# Or check run history
vastde pipelines describe exr-inspect-pipeline
```

Expected pipeline status:
```
Pipeline: exr-inspect-pipeline
Status: Running
Trigger: S3 object create on exr-input-data/*.exr
Function: exr-inspector (v1.0.0)
Last Run: 2 minutes ago
Files Processed: 2
Status: Success
```

---

## Step 5: Query Results

**Estimated Time: 15 minutes**

Once the pipeline processes files, metadata is available in VAST DataBase for analysis and reporting.

### 5A. Connect to VAST DataBase

**Using Python SDK:**

```python
import os
from vastdb import VastdbConnector

# Configuration
endpoint = os.getenv("VAST_DB_ENDPOINT", "s3.region.vastdata.com")
access_key = os.getenv("VAST_DB_ACCESS_KEY")
secret_key = os.getenv("VAST_DB_SECRET_KEY")

# Connect
connector = VastdbConnector(
    endpoint=endpoint,
    access_key_id=access_key,
    secret_access_key=secret_key,
    region="us-east-1",
    use_ssl=True,
)

# Get schema and tables
bucket = connector.get_bucket("exr-metadata-prod")
schema = bucket.get_schema("exr_metadata")

files_table = schema.get_table("files")
parts_table = schema.get_table("parts")
channels_table = schema.get_table("channels")
```

### 5B: Example Analytics Queries

#### Query 1: List All Processed Files

```python
# Get all files
results = files_table.select_all(limit=100)
for row in results:
    print(f"{row['file_path']}: {row['size_bytes']} bytes, "
          f"{row['multipart_count']} parts, "
          f"inspected {row['inspection_count']} times")
```

Expected output:
```
/renders/shot_001.exr: 2097152 bytes, 2 parts, inspected 1 times
/renders/shot_002.exr: 1843200 bytes, 2 parts, inspected 1 times
/renders/shot_003.exr: 3145728 bytes, 1 part, inspected 1 times
```

#### Query 2: Find Files by Compression Type

```python
# Find all files with specific compression
results = parts_table.select_by_filter(
    filter_clause="compression = 'zip'",
    limit=50
)

compression_stats = {}
for row in results:
    comp = row['compression']
    compression_stats[comp] = compression_stats.get(comp, 0) + 1

for comp, count in sorted(compression_stats.items(),
                         key=lambda x: x[1], reverse=True):
    print(f"{comp}: {count} parts")
```

Expected output:
```
zip: 4 parts
piz: 2 parts
none: 1 part
```

#### Query 3: Deep EXR Analysis

```python
# Find all deep EXR files
results = files_table.select_by_filter(
    filter_clause="is_deep = true",
)

print(f"Deep EXR files: {len(results)}")
for row in results:
    print(f"  {row['file_path']}: {row['size_bytes']} bytes")
```

#### Query 4: Channel Configuration

```python
# Count channels per file
results = channels_table.select_all()

channel_counts = {}
for row in results:
    file_id = row['file_id']
    channel_counts[file_id] = channel_counts.get(file_id, 0) + 1

avg_channels = sum(channel_counts.values()) / len(channel_counts)
print(f"Average channels per file: {avg_channels:.1f}")
print(f"Max channels in single file: {max(channel_counts.values())}")
```

#### Query 5: Inspection Frequency

```python
# Find files inspected multiple times
results = files_table.select_by_filter(
    filter_clause="inspection_count > 1",
)

print(f"Files re-inspected: {len(results)}")
for row in results:
    print(f"  {row['file_path']}: inspected {row['inspection_count']} times")
```

### 5C: Vector Search

Find files with similar metadata structures:

```python
import numpy as np

# Get reference file
ref_results = files_table.select_by_filter(
    filter_clause="file_path LIKE '%shot_001%'",
    limit=1
)
ref_embedding = np.array(ref_results[0]['metadata_embedding'])

# Find similar files using vector distance
# (Note: VAST DataBase vector search API varies by version)
results = files_table.search_vector(
    vector_column="metadata_embedding",
    query_vector=ref_embedding,
    metric="cosine",
    limit=5
)

print("Files with similar metadata structures:")
for row in results:
    print(f"  {row['file_path']}")
```

### 5D: Export Results for Analytics

```python
import pandas as pd
import json

# Export to CSV
results = files_table.select_all()
df = pd.DataFrame([dict(row) for row in results])
df.to_csv("exr_metadata.csv", index=False)
print(f"Exported {len(df)} files to exr_metadata.csv")

# Export to JSON
export_data = {
    "exported_at": pd.Timestamp.now().isoformat(),
    "file_count": len(df),
    "files": [dict(row) for row in results],
}
with open("exr_metadata.json", "w") as f:
    json.dump(export_data, f, indent=2)
```

---

## Troubleshooting

### Function Build Issues

#### Problem: "vastde functions build" fails with "Docker not installed"

**Solution:**
```bash
# Verify Docker is running
docker ps

# If not installed, install Docker Desktop or Docker Engine
# https://docs.docker.com/get-docker/

# Retry build
vastde functions build exr-inspector -target ./exr_inspector --image-tag exr-inspector
```

#### Problem: "Missing system dependencies" error during build

**Solution:**
Ensure `Aptfile` is present and contains system library declarations:

```bash
cat ~/functions/exr_inspector/Aptfile
```

Should list:
```
libopenimageio-dev
libopenexr-dev
```

If missing, add them:
```bash
echo "libopenimageio-dev" >> ~/functions/exr_inspector/Aptfile
echo "libopenexr-dev" >> ~/functions/exr_inspector/Aptfile
```

Retry build.

### Registry Push Issues

#### Problem: "Authentication failed" when pushing to Docker Hub

**Solution:**
```bash
# Log in interactively
docker login -u your-username
# Enter password when prompted

# Verify credentials
cat ~/.docker/config.json | grep auths

# Retry push
docker push docker.io/my-org/exr-inspector:v1.0.0
```

#### Problem: "Image not found" in VAST UI after push

**Solution:**
1. Verify image tag matches exactly in VAST UI:
   ```bash
   docker images exr-inspector
   # Compare tag with "Image Tag" field in VAST
   ```

2. Check registry connectivity:
   ```bash
   vastde registry test --registry docker.io
   ```

3. Manually pull image to verify:
   ```bash
   docker pull docker.io/my-org/exr-inspector:v1.0.0
   ```

### Database Schema Issues

#### Problem: "Table not found" or "Schema not found" error in logs

**Solution:**
Verify schema was created:

```bash
python << 'EOF'
from vastdb import VastdbConnector
import os

connector = VastdbConnector(
    endpoint=os.getenv("VAST_DB_ENDPOINT"),
    access_key_id=os.getenv("VAST_DB_ACCESS_KEY"),
    secret_access_key=os.getenv("VAST_DB_SECRET_KEY"),
)

bucket = connector.get_bucket("exr-metadata-prod")
schemas = bucket.list_schemas()
print(f"Available schemas: {schemas}")

if "exr_metadata" in schemas:
    schema = bucket.get_schema("exr_metadata")
    tables = schema.list_tables()
    print(f"Tables in exr_metadata: {tables}")
else:
    print("ERROR: exr_metadata schema not found. Run Step 1 again.")
EOF
```

If schema missing, recreate it (see Step 1).

#### Problem: "Connection refused" or timeout

**Solution:**
1. Verify endpoint is reachable:
   ```bash
   ping -c 3 s3.region.vastdata.com
   ```

2. Test with telnet or curl:
   ```bash
   curl -I https://s3.region.vastdata.com/
   ```

3. Check credentials:
   ```bash
   aws s3 ls --endpoint-url https://s3.region.vastdata.com \
     --region us-east-1 \
     --access-key VAST_DB_ACCESS_KEY \
     --secret-key VAST_DB_SECRET_KEY
   ```

4. Check firewall/security group rules allow outbound HTTPS (443)

### Credential Issues

#### Problem: "Invalid credentials" error in function logs

**Solution:**
1. Verify environment variables are set:
   ```bash
   vastde functions describe exr-inspector
   # Check "Environment Variables" section
   ```

2. Re-set credentials:
   ```bash
   vastde functions set-env exr-inspector \
     --env VAST_DB_ACCESS_KEY=<new-key> \
     --env VAST_DB_SECRET_KEY=<new-secret>
   ```

3. Check credentials in VAST DataBase:
   - Log in to VAST UI
   - Go to **Settings → Authentication**
   - Verify user has DataBase access

### Trigger & Pipeline Issues

#### Problem: Pipeline doesn't start after S3 upload

**Solution:**
1. Check S3 bucket trigger configuration:
   ```bash
   vastde pipelines describe exr-inspect-pipeline
   # Look for "Trigger Status"
   ```

2. Test trigger manually:
   ```bash
   # List pipeline runs
   vastde pipelines list-runs exr-inspect-pipeline

   # Get details of last run
   vastde pipelines describe exr-inspect-pipeline --run latest
   ```

3. Check S3 bucket permissions:
   - Bucket must allow VAST to read objects
   - Bucket events must be configured for `s3:ObjectCreated`

4. Verify file matches trigger filter:
   - Suffix: `.exr` (case-sensitive)
   - Prefix: `/renders/` if specified

#### Problem: Function runs but produces no output

**Solution:**
Check function logs:

```bash
# Stream recent logs
vastde functions logs exr-inspector --tail 20

# Or check via UI:
# Manage Elements → Functions → exr-inspector → Logs
```

Look for error messages. Common issues:
- File not found (check EXR file path in trigger)
- OpenImageIO import error (missing system libraries)
- VAST DataBase connection error (credentials or endpoint)

### Query Issues

#### Problem: "No results" when querying VAST DataBase

**Solution:**
1. Verify files were persisted:
   ```python
   from vastdb import VastdbConnector
   import os

   connector = VastdbConnector(...)
   schema = connector.get_bucket("...").get_schema("exr_metadata")
   files_table = schema.get_table("files")

   count = files_table.count()
   print(f"Total files in database: {count}")
   ```

2. Check if pipeline run completed successfully:
   ```bash
   vastde pipelines describe exr-inspect-pipeline --run latest
   ```

3. Verify function returned success status:
   ```bash
   vastde pipelines logs exr-inspect-pipeline | grep -i "success\|error"
   ```

### Performance Issues

#### Problem: Pipeline is slow or times out

**Solution:**
1. Check cluster load:
   ```bash
   vastde cluster status
   ```

2. Reduce batch size if processing many files:
   - Configure trigger to process one file at a time (vs bulk)
   - Add delay between invocations

3. Check network latency to VAST DataBase:
   ```bash
   ping s3.region.vastdata.com
   # Should be < 50ms from VAST cluster
   ```

---

## Next Steps

### 1. Enable Additional Analysis Features

The exr-inspector function supports additional features you can enable:

**In function event payload:**

```json
{
  "data": {
    "path": "/path/to/file.exr"
  },
  "enable_meta": true,
  "enable_stats": false,
  "enable_deep_stats": false,
  "enable_validate": false
}
```

- **enable_stats**: Compute per-channel pixel statistics (min/max/mean/stddev)
- **enable_deep_stats**: Advanced deep EXR analysis
- **enable_validate**: Run policy-driven validation (requires policy definition)

### 2: Set Up Monitoring & Alerting

Configure VAST alerting for pipeline failures:

```bash
# Create alert for failed runs
vastde alerts create \
  --name "exr-pipeline-failure" \
  --condition "pipeline_status == FAILED" \
  --notify "your-email@studio.com"

# Monitor pipeline metrics
vastde metrics export exr-inspect-pipeline --format prometheus
```

### 3: Create Validation Policies

Define studio standards for EXR files (future release):

```yaml
# exr-validation-policy.yaml
---
validation_rules:
  compression:
    allowed: [zip, piz, none]
    required: true

  channel_config:
    required_channels: [R, G, B, A]
    max_channels: 16

  metadata:
    required_attributes:
      - creator
      - datetime
      - author

  color_space:
    standard: "sRGB"
    allow_linear: true
```

### 4: Analyze Results in BI Tools

Export VAST DataBase data to analytics platforms:

```bash
# Export to Parquet for Spark/Tableau
vastdb export \
  --schema exr_metadata \
  --tables files,parts,channels \
  --format parquet \
  --output gs://analytics/exr_metadata_parquet
```

### 5: Set Up Continuous Monitoring

Create dashboards to track:
- Files processed per day
- Compression type distribution
- Channel configuration trends
- Validation pass rates
- Storage consumption

Example query for dashboard:
```python
# Daily processing volume
results = files_table.select_by_filter(
    filter_clause="last_inspected >= DATE_SUB(NOW(), INTERVAL 1 DAY)",
)
print(f"Files processed today: {len(results)}")
```

### 6: Integrate with Downstream Systems

Use VAST DataBase as source of truth for:
- **Asset management**: Track file versions and lineage
- **Studio pipelines**: Lookup metadata for render jobs
- **QA systems**: Validate files before publishing
- **ML workflows**: Use embeddings for content similarity

Example integration:
```python
# In your asset management system
from vastdb import VastdbConnector

def get_file_metadata(file_path):
    connector = get_vastdb_connector()
    schema = connector.get_bucket(...).get_schema("exr_metadata")
    files = schema.get_table("files")

    result = files.select_by_filter(
        filter_clause=f"file_path = '{file_path}'"
    )
    return result[0] if result else None
```

---

## Appendix: Reference Documentation

### Environment Variables

| Variable | Required | Default | Example |
|----------|----------|---------|---------|
| `VAST_DB_ENDPOINT` | Yes | — | `s3.region.vastdata.com` |
| `VAST_DB_ACCESS_KEY` | Yes | — | (AWS-style access key) |
| `VAST_DB_SECRET_KEY` | Yes | — | (AWS-style secret key) |
| `VAST_DB_REGION` | No | `us-east-1` | `us-west-2` |
| `VAST_DB_SCHEMA` | No | `exr_metadata` | `exr_inspect_prod` |

### Function Input Schema

```json
{
  "data": {
    "path": "string (required)",
    "meta": "boolean (optional, default: true)"
  },
  "enable_meta": "boolean (optional, default: true)",
  "enable_stats": "boolean (optional, default: false)",
  "enable_deep_stats": "boolean (optional, default: false)",
  "enable_validate": "boolean (optional, default: false)"
}
```

### Function Output Schema

```json
{
  "schema_version": 1,
  "file": {
    "path": "string",
    "size_bytes": "integer",
    "mtime": "ISO8601 timestamp"
  },
  "parts": [
    {
      "index": "integer",
      "name": "string",
      "width": "integer",
      "height": "integer",
      "compression": "string",
      "is_tiled": "boolean"
    }
  ],
  "channels": [
    {
      "part_index": "integer",
      "name": "string",
      "type": "string",
      "x_sampling": "integer",
      "y_sampling": "integer"
    }
  ],
  "attributes": {
    "key": "value (various types)"
  },
  "persistence": {
    "status": "success|error|skipped",
    "file_id": "string",
    "inserted": "boolean",
    "message": "string",
    "error": "string|null"
  },
  "errors": ["string"]
}
```

### Database Schema Details

See `/functions/exr_inspector/VAST_DB_INTEGRATION.md` for detailed:
- Table schemas (columns, types, constraints)
- Vector embedding specifications
- Query examples
- Performance tuning tips

### Related Documentation

- **`README.md`**: Project overview and features
- **`PRD.md`**: Product requirements and design rationale
- **`docs/vast-integration.md`**: VAST integration architecture
- **`functions/exr_inspector/VAST_DB_INTEGRATION.md`**: Detailed persistence documentation
- **`functions/exr_inspector/README.md`**: Function-specific reference

---

## Support & Issues

### Getting Help

1. **Check logs first**: Most issues visible in function logs
   ```bash
   vastde functions logs exr-inspector --tail 50
   vastde pipelines logs exr-inspect-pipeline --follow
   ```

2. **Review error messages**: Function returns detailed error context in JSON output

3. **Consult related docs**: See Reference Documentation above

4. **Contact VAST support**: For cluster, registry, or authentication issues

### Reporting Issues

When reporting problems, include:
- Function logs (stderr/stdout)
- Event payload that triggered issue
- Expected vs actual output
- Environment variables (with sensitive values redacted)
- VAST cluster version and configuration

---

**Last Updated**: February 2025
**exr-inspector Version**: v1.0.0+
**VAST Compatibility**: v5.0.0-sp10 or later
