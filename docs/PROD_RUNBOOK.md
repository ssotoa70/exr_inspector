# exr-inspector: Production Deployment Runbook

**For DevOps/SRE teams deploying exr-inspector to production with VAST DataEngine and DataBase**

Estimated total deployment time: 60-90 minutes (first time), 20-30 minutes (subsequent deployments).

---

## Table of Contents

1. [Prerequisites & Verification (10 min)](#prerequisites--verification)
2. [Phase 1: Schema & Database Setup (15 min)](#phase-1-schema--database-setup)
3. [Phase 2: Build & Container Registry (15 min)](#phase-2-build--container-registry)
4. [Phase 3: Function Deployment (10 min)](#phase-3-function-deployment)
5. [Phase 4: Trigger & Pipeline Configuration (10 min)](#phase-4-trigger--pipeline-configuration)
6. [Phase 5: Verification & Smoke Tests (10 min)](#phase-5-verification--smoke-tests)
7. [Monitoring & Observability (5 min)](#monitoring--observability)
8. [Rollback Procedures](#rollback-procedures)
9. [Production Checklist](#production-checklist)

---

## Prerequisites & Verification

**Estimated Time: 10 minutes**

Before starting, verify all prerequisites are in place.

### Pre-Deployment Checklist

Complete this checklist before beginning deployment:

- [ ] VAST cluster access confirmed (v5.0.0-sp10 or later)
- [ ] VAST DataEngine CLI (`vastde`) installed and configured
- [ ] Docker installed and running
- [ ] Container registry access verified (push credentials ready)
- [ ] VAST DataBase endpoint and credentials obtained
- [ ] S3/object storage bucket configured for input EXR files
- [ ] Network connectivity verified (cluster reachable from deployment machine)
- [ ] All team members notified of deployment window
- [ ] Staging environment tested (optional but recommended)

### System Requirements Verification

```bash
# Check VAST DataEngine CLI
vastde --version
# Expected: vastde version 5.0.0-sp10 or later

# Check Docker
docker --version
# Expected: Docker version 20.10 or later

# Check Python (if building locally)
python3 --version
# Expected: Python 3.9 or 3.10

# Check git
git --version
# Expected: git version 2.0 or later

# Verify VAST cluster connectivity
ping -c 3 your-vast-cluster.example.com
# Expected: responses with < 100ms latency

# Verify VAST DataBase endpoint
curl -I https://s3.region.vastdata.com/
# Expected: 200, 403, or 401 (not 404 or timeout)
```

### Credentials Preparation

Collect and securely store the following information:

```bash
# 1. VAST DataBase Credentials
VAST_DB_ENDPOINT="s3.region.vastdata.com"
VAST_DB_ACCESS_KEY="<your-access-key>"
VAST_DB_SECRET_KEY="<your-secret-key>"
VAST_DB_REGION="us-east-1"
VAST_DB_SCHEMA="exr_metadata"

# 2. Container Registry Credentials
REGISTRY_HOST="docker.io"           # or ECR, Harbor, etc.
REGISTRY_ORG="your-org"
REGISTRY_USERNAME="<your-username>"
REGISTRY_PASSWORD="<secure-token>"  # Store in secure vault

# 3. S3 Input Bucket
S3_INPUT_BUCKET="exr-input-data"
S3_BUCKET_REGION="us-east-1"
S3_ACCESS_KEY="<s3-access-key>"
S3_SECRET_KEY="<s3-secret-key>"
```

**Secure Storage:**
```bash
# Example: Use .env file (add to .gitignore)
cat > .env.prod << 'EOF'
export VAST_DB_ENDPOINT="s3.region.vastdata.com"
export VAST_DB_ACCESS_KEY="..."
export VAST_DB_SECRET_KEY="..."
# ... more variables
EOF

# Load when needed (do not commit)
source .env.prod

# Or use Docker secrets (recommended for production)
# docker secret create vast_db_endpoint <(echo "s3.region.vastdata.com")
```

### Staging Environment Test (Optional)

Before production, test in staging:

```bash
# Clone production schema to staging
vastde schema clone \
    --source exr_metadata \
    --target exr_metadata_staging

# Deploy to staging first
vastde function deploy exr-inspector \
    --version v1.0.0 \
    --environment staging

# Run smoke tests in staging
python scripts/staging_smoke_test.py \
    --schema exr_metadata_staging \
    --sample-files 5
```

If staging test succeeds, proceed to production.

---

## Phase 1: Schema & Database Setup

**Estimated Time: 15 minutes**

Create the VAST DataBase schema and tables. This step is only needed once per environment.

### Step 1A: Verify VAST DataBase Access

```bash
# Test connectivity to VAST DataBase
python3 << 'EOF'
import os
from vastdb_sdk import Session

try:
    endpoint = os.getenv("VAST_DB_ENDPOINT")
    access_key = os.getenv("VAST_DB_ACCESS_KEY")
    secret_key = os.getenv("VAST_DB_SECRET_KEY")

    if not all([endpoint, access_key, secret_key]):
        print("ERROR: Missing VAST_DB_* environment variables")
        exit(1)

    session = Session(
        endpoint=endpoint,
        access_key_id=access_key,
        secret_access_key=secret_key,
        region=os.getenv("VAST_DB_REGION", "us-east-1"),
        use_ssl=True,
    )

    print(f"✓ Connected to VAST DataBase: {endpoint}")

except Exception as e:
    print(f"✗ Connection failed: {e}")
    exit(1)
EOF
```

Expected output:
```
✓ Connected to VAST DataBase: s3.region.vastdata.com
```

### Step 1B: Create Schema and Tables

Use the production schema creation script:

```bash
cd /path/to/exr-inspector

# Create schema initialization script
python3 << 'EOF'
"""
Create VAST DataBase schema for exr-inspector (production).
"""

import os
import sys
import logging
from datetime import datetime
import pyarrow as pa
from vastdb_sdk import Session

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration
endpoint = os.getenv("VAST_DB_ENDPOINT")
access_key = os.getenv("VAST_DB_ACCESS_KEY")
secret_key = os.getenv("VAST_DB_SECRET_KEY")
region = os.getenv("VAST_DB_REGION", "us-east-1")
schema_name = os.getenv("VAST_DB_SCHEMA", "exr_metadata")
bucket_name = "exr-metadata-prod"

if not all([endpoint, access_key, secret_key]):
    logger.error("Missing VAST_DB_* environment variables")
    sys.exit(1)

try:
    logger.info(f"Connecting to VAST DataBase: {endpoint}")
    session = Session(
        endpoint=endpoint,
        access_key_id=access_key,
        secret_access_key=secret_key,
        region=region,
        use_ssl=True,
    )

    logger.info(f"Getting bucket: {bucket_name}")
    bucket = session.get_bucket(bucket_name)

    # Create schema
    logger.info(f"Creating schema: {schema_name}")
    schema = bucket.create_schema(schema_name)

    # Define table schemas
    logger.info("Defining table schemas...")

    files_schema = pa.schema([
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
    ])

    parts_schema = pa.schema([
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
        ("is_deep", pa.bool_()),
    ])

    channels_schema = pa.schema([
        ("file_id", pa.string()),
        ("file_path", pa.string()),
        ("part_index", pa.int32()),
        ("channel_name", pa.string()),
        ("channel_type", pa.string()),
        ("x_sampling", pa.int32()),
        ("y_sampling", pa.int32()),
        ("channel_fingerprint", pa.list_(pa.float32(), 128)),
    ])

    attributes_schema = pa.schema([
        ("file_id", pa.string()),
        ("file_path", pa.string()),
        ("part_index", pa.int32()),
        ("attribute_name", pa.string()),
        ("attribute_type", pa.string()),
        ("attribute_value", pa.string()),
    ])

    # Create tables
    logger.info("Creating tables...")
    schema.create_table("files", files_schema)
    logger.info("  ✓ files table created")

    schema.create_table("parts", parts_schema)
    logger.info("  ✓ parts table created")

    schema.create_table("channels", channels_schema)
    logger.info("  ✓ channels table created")

    schema.create_table("attributes", attributes_schema)
    logger.info("  ✓ attributes table created")

    # Create indexes for performance
    logger.info("Creating indexes...")
    try:
        session.execute(f"""
            CREATE INDEX idx_files_path_normalized
            ON {schema_name}.files (file_path_normalized)
        """)
        logger.info("  ✓ files path index created")
    except:
        logger.warning("  ⚠ files path index creation skipped (may already exist)")

    try:
        session.execute(f"""
            CREATE INDEX idx_files_is_deep
            ON {schema_name}.files (is_deep)
        """)
        logger.info("  ✓ files is_deep index created")
    except:
        logger.warning("  ⚠ files is_deep index creation skipped (may already exist)")

    logger.info(f"\n✓ SUCCESS: Schema '{schema_name}' created with 4 tables and indexes")
    logger.info(f"Timestamp: {datetime.utcnow().isoformat()}Z")

except Exception as e:
    logger.error(f"✗ FAILED: {e}", exc_info=True)
    sys.exit(1)
EOF
```

Save this as `scripts/create_schema_prod.py` and run:

```bash
# Load environment variables
source .env.prod

# Run schema creation
python3 scripts/create_schema_prod.py

# Expected output:
# 2025-02-06 14:30:45,123 - INFO - Connecting to VAST DataBase: s3.region.vastdata.com
# 2025-02-06 14:30:46,456 - INFO - Creating schema: exr_metadata
# 2025-02-06 14:30:47,789 - INFO - Creating tables...
# 2025-02-06 14:30:48,012 - INFO -   ✓ files table created
# ...
# 2025-02-06 14:30:50,234 - INFO - ✓ SUCCESS: Schema 'exr_metadata' created with 4 tables and indexes
```

### Step 1C: Verify Schema Creation

```bash
python3 << 'EOF'
import os
from vastdb_sdk import Session

session = Session(
    endpoint=os.getenv("VAST_DB_ENDPOINT"),
    access_key_id=os.getenv("VAST_DB_ACCESS_KEY"),
    secret_access_key=os.getenv("VAST_DB_SECRET_KEY"),
    region=os.getenv("VAST_DB_REGION", "us-east-1"),
    use_ssl=True,
)

bucket = session.get_bucket("exr-metadata-prod")
schema = bucket.get_schema("exr_metadata")

tables = schema.list_tables()
print(f"Tables in 'exr_metadata' schema:")
for table_name in sorted(tables):
    table = schema.get_table(table_name)
    col_count = len(table.schema.names)
    print(f"  ✓ {table_name}: {col_count} columns")

# Verify row count (should be 0 for new schema)
files_table = schema.get_table("files")
results = files_table.select_all(limit=1)
print(f"\nInitial row count: {len(results)} (expected: 0)")
EOF
```

Expected output:
```
Tables in 'exr_metadata' schema:
  ✓ attributes: 5 columns
  ✓ channels: 8 columns
  ✓ files: 12 columns
  ✓ parts: 15 columns

Initial row count: 0 (expected: 0)
```

---

## Phase 2: Build & Container Registry

**Estimated Time: 15 minutes**

Build the exr-inspector Docker container and push to your registry.

### Step 2A: Build Container Image

```bash
# Prepare build environment
cd /path/to/exr-inspector
mkdir -p ~/functions/exr_inspector

# Copy function files to build directory
cp functions/exr_inspector/main.py ~/functions/exr_inspector/
cp functions/exr_inspector/vast_db_persistence.py ~/functions/exr_inspector/
cp functions/exr_inspector/requirements.txt ~/functions/exr_inspector/
cp functions/exr_inspector/Aptfile ~/functions/exr_inspector/

# Verify files are present
ls -la ~/functions/exr_inspector/
```

Expected output:
```
-rw-r--r--  1 user  staff    10153 Feb  6 14:00 main.py
-rw-r--r--  1 user  staff    34662 Feb  6 14:00 vast_db_persistence.py
-rw-r--r--  1 user  staff      128 Feb  6 14:00 requirements.txt
-rw-r--r--  1 user  staff       34 Feb  6 14:00 Aptfile
```

Now build the image:

```bash
cd ~/functions

# Build container image
vastde functions build exr-inspector \
    --target ./exr_inspector \
    --image-tag exr-inspector:v1.0.0

# Expected output:
# [1/4] Building Docker image...
# [2/4] Installing dependencies...
#       • Installing Python packages from requirements.txt
#       • Installing system packages from Aptfile
# [3/4] Optimizing layers...
# [4/4] Complete
# Successfully built: exr-inspector:v1.0.0 (256MB)
```

Verify the build:

```bash
docker images exr-inspector
```

Expected output:
```
REPOSITORY       TAG         IMAGE ID      CREATED       SIZE
exr-inspector    v1.0.0      abc123def456  2 minutes ago  256MB
```

**Build Troubleshooting:**

If build fails with "Docker not found":
```bash
# Verify Docker is running
docker ps

# On macOS, may need to start Docker Desktop
# Or verify daemon socket
ls -la /var/run/docker.sock
```

If build fails with "Missing system dependencies":
```bash
# Verify Aptfile contains required packages
cat ~/functions/exr_inspector/Aptfile

# Should contain:
# libopenimageio-dev
# libopenexr-dev

# If missing, add them:
echo "libopenimageio-dev" >> ~/functions/exr_inspector/Aptfile
echo "libopenexr-dev" >> ~/functions/exr_inspector/Aptfile

# Rebuild
vastde functions build exr-inspector --target ./exr_inspector --image-tag exr-inspector:v1.0.0
```

### Step 2B: Push to Container Registry

Determine your registry type and follow the appropriate steps.

**Docker Hub:**

```bash
# Log in to Docker Hub
docker login -u your-username

# Tag image for Docker Hub
docker tag exr-inspector:v1.0.0 docker.io/your-org/exr-inspector:v1.0.0
docker tag exr-inspector:v1.0.0 docker.io/your-org/exr-inspector:latest

# Push to registry
docker push docker.io/your-org/exr-inspector:v1.0.0
docker push docker.io/your-org/exr-inspector:latest

# Verify push
docker images | grep exr-inspector
```

**AWS ECR:**

```bash
# Get login token
aws ecr get-login-password --region us-east-1 | \
    docker login --username AWS --password-stdin 123456789.dkr.ecr.us-east-1.amazonaws.com

# Tag image for ECR
docker tag exr-inspector:v1.0.0 \
    123456789.dkr.ecr.us-east-1.amazonaws.com/exr-inspector:v1.0.0

# Push to ECR
docker push 123456789.dkr.ecr.us-east-1.amazonaws.com/exr-inspector:v1.0.0

# Verify push
aws ecr describe-images --repository-name exr-inspector
```

**Private Registry (Harbor, Nexus, etc.):**

```bash
# Log in
docker login my-registry.example.com:5000

# Tag image
docker tag exr-inspector:v1.0.0 my-registry.example.com:5000/exr-inspector:v1.0.0

# Push
docker push my-registry.example.com:5000/exr-inspector:v1.0.0

# Verify push
curl -u username:password https://my-registry.example.com:5000/v2/exr-inspector/tags/list
```

### Step 2C: Verify Registry Access

```bash
# Test pulling the image from registry (simulates what VAST will do)
docker pull docker.io/your-org/exr-inspector:v1.0.0

# Or from ECR
aws ecr describe-images --repository-name exr-inspector --region us-east-1
```

Expected output (Docker Hub):
```
v1.0.0: Pulling from your-org/exr-inspector
Digest: sha256:abc123...
Status: Downloaded newer image for docker.io/your-org/exr-inspector:v1.0.0
```

---

## Phase 3: Function Deployment

**Estimated Time: 10 minutes**

Deploy the function to VAST DataEngine.

### Step 3A: Create Function in VAST UI

1. **Log in to VAST cluster:**
   ```bash
   vastde login --endpoint https://your-vast-cluster.example.com
   ```

2. **Create function via UI:**
   - Navigate to **Manage Elements → Functions**
   - Click **Create New Function**
   - Fill in the following:

   | Field | Value |
   |-------|-------|
   | **Name** | `exr-inspector` |
   | **Description** | `EXR file metadata extraction with VAST DataBase persistence` |
   | **Revision Alias** | `v1.0.0` |
   | **Container Registry** | `docker.io` (or your registry) |
   | **Artifact Source** | `your-org/exr-inspector` |
   | **Image Tag** | `v1.0.0` |
   | **Full Image Path** | (auto-generated) |

3. **Click "Create Function"**

Expected status:
```
Function 'exr-inspector' created successfully
Status: Ready
Version: v1.0.0
```

### Step 3B: Configure Environment Variables

Set credentials that the function will use at runtime:

```bash
# Via VAST CLI
vastde functions set-env exr-inspector \
    --env VAST_DB_ENDPOINT="s3.region.vastdata.com" \
    --env VAST_DB_ACCESS_KEY="your-access-key" \
    --env VAST_DB_SECRET_KEY="your-secret-key" \
    --env VAST_DB_REGION="us-east-1" \
    --env VAST_DB_SCHEMA="exr_metadata"
```

Or via VAST UI:
1. Go to **Manage Elements → Functions → exr-inspector**
2. Click **Edit Environment Variables**
3. Add the variables above
4. Click **Save**

Verify environment variables:

```bash
vastde functions describe exr-inspector
# Look for "Environment Variables" section
```

### Step 3C: Test Function Invocation

Create a test event and invoke the function:

```bash
# Create test event file
cat > /tmp/test_event.json << 'EOF'
{
  "data": {
    "path": "/data/test.exr"
  }
}
EOF

# Invoke function (test locally first)
vastde functions localrun exr-inspector --event /tmp/test_event.json

# Expected output:
# {
#   "schema_version": 1,
#   "file": {"path": "/data/test.exr", "size_bytes": ...},
#   "parts": [...],
#   "channels": [...],
#   "attributes": {...},
#   "persistence": {"status": "success", "file_id": "abc123..."}
# }
```

If local test succeeds, function is ready for pipeline integration.

---

## Phase 4: Trigger & Pipeline Configuration

**Estimated Time: 10 minutes**

Configure event-driven triggers so the function runs automatically on S3 uploads.

### Step 4A: Create Pipeline

1. **In VAST DataEngine UI:**
   - Navigate to **Pipelines**
   - Click **Create New Pipeline**

2. **Enter details:**
   - **Name**: `exr-inspect-pipeline`
   - **Description**: `Automatically inspect EXR files on S3 upload`

3. **Add stage:**
   - Click **Add Stage**
   - Select **exr-inspector** function
   - Confirm revision: **v1.0.0**

### Step 4B: Configure S3 Trigger

1. **Click "Add Trigger"**

2. **Select trigger type:** `S3 Object Create`

3. **Configure S3 connection:**
   - **S3 Endpoint**: S3 bucket endpoint
   - **Bucket Name**: `exr-input-data`
   - **Access Key**: S3 access key
   - **Secret Key**: S3 secret key
   - **Region**: `us-east-1` (or your region)

4. **Configure filter:**
   - **Prefix**: `/renders/` (optional, to filter subdirectory)
   - **Suffix**: `.exr` (to only trigger on EXR files)
   - **Events**: `s3:ObjectCreated:*`

5. **Click "Verify Trigger"**

Expected output:
```
Trigger verified successfully
S3 bucket is accessible
Permissions verified
```

### Step 4C: Deploy Pipeline

1. **Click "Deploy Pipeline"**

2. **Monitor initial deployment:**
   - Status changes from "Pending" to "Running"
   - First run may process existing objects in bucket

3. **Check pipeline status:**
   ```bash
   vastde pipelines describe exr-inspect-pipeline
   ```

   Expected output:
   ```
   Pipeline: exr-inspect-pipeline
   Status: Running
   Trigger: S3 object create on exr-input-data/*.exr
   Function: exr-inspector (v1.0.0)
   Last Run: 5 minutes ago
   Files Processed: 0 (pending first trigger)
   ```

### Step 4D: Monitor Initial Run

```bash
# Stream logs from pipeline
vastde pipelines logs exr-inspect-pipeline --follow

# Or get recent logs
vastde pipelines logs exr-inspect-pipeline --tail 50
```

Expected log output:
```
[2025-02-06 14:45:30] INFO Starting pipeline: exr-inspect-pipeline
[2025-02-06 14:45:31] INFO Waiting for S3 events...
[2025-02-06 14:45:45] INFO S3 object created: s3://exr-input-data/renders/shot_001.exr
[2025-02-06 14:45:46] INFO Invoking function: exr-inspector
[2025-02-06 14:45:50] INFO Function output: extracted 8 channels, 2 parts
[2025-02-06 14:45:51] INFO Persisted to VAST DataBase: file_id=abc123def456
[2025-02-06 14:45:52] INFO Pipeline run completed successfully
```

---

## Phase 5: Verification & Smoke Tests

**Estimated Time: 10 minutes**

Verify that the entire pipeline is working correctly.

### Step 5A: Trigger Test File

Upload a test EXR file to verify the pipeline:

```bash
# Copy test file to S3 input bucket
aws s3 cp /path/to/test.exr s3://exr-input-data/renders/test_deployment.exr \
    --endpoint-url https://s3.region.vastdata.com \
    --region us-east-1

# Expected:
# upload: /path/to/test.exr to s3://exr-input-data/renders/test_deployment.exr
```

### Step 5B: Monitor Function Execution

```bash
# Watch function logs in real-time
vastde functions logs exr-inspector --tail 20 --follow

# Expected output:
# [INFO] Handler invoked for file: s3://exr-input-data/renders/test_deployment.exr
# [INFO] Extracting metadata...
# [INFO] Computed embedding: 384D vector
# [INFO] Persisting to VAST DataBase...
# [INFO] Success: file_id=abc123...
```

### Step 5C: Verify Data in Database

Query the database to confirm metadata was persisted:

```bash
python3 << 'EOF'
import os
from vastdb_sdk import Session

session = Session(
    endpoint=os.getenv("VAST_DB_ENDPOINT"),
    access_key_id=os.getenv("VAST_DB_ACCESS_KEY"),
    secret_access_key=os.getenv("VAST_DB_SECRET_KEY"),
    region=os.getenv("VAST_DB_REGION", "us-east-1"),
    use_ssl=True,
)

bucket = session.get_bucket("exr-metadata-prod")
schema = bucket.get_schema("exr_metadata")

# Get tables
files_table = schema.get_table("files")
parts_table = schema.get_table("parts")
channels_table = schema.get_table("channels")

# Query recent files
print("Recent files:")
results = files_table.select_all(limit=5)
for row in results:
    print(f"  - {row['file_path']}: {row['size_bytes']} bytes, "
          f"{row['multipart_count']} parts, "
          f"embedding: {len(row['metadata_embedding'])}D")

# Count records
print(f"\nDatabase summary:")
print(f"  Files: {files_table.count()} rows")
print(f"  Parts: {parts_table.count()} rows")
print(f"  Channels: {channels_table.count()} rows")
EOF
```

Expected output:
```
Recent files:
  - s3://exr-input-data/renders/test_deployment.exr: 1048576 bytes, 2 parts, embedding: 384D

Database summary:
  Files: 1 rows
  Parts: 2 rows
  Channels: 8 rows
```

### Step 5D: Smoke Test Checklist

Before marking deployment complete, verify:

- [ ] **Schema created**: All 4 tables present in VAST DataBase
- [ ] **Function deployed**: `exr-inspector` v1.0.0 shows "Ready" status
- [ ] **Environment variables set**: All VAST_DB_* variables present
- [ ] **Trigger configured**: Pipeline shows "Running" status
- [ ] **Test file processed**: S3 object triggered pipeline execution
- [ ] **Function logs clear**: No error messages in recent logs
- [ ] **Data persisted**: Query returns at least 1 row in files table
- [ ] **Embeddings present**: Metadata embedding vectors are 384D

All checkmarks required before production acceptance.

---

## Monitoring & Observability

**Estimated Time: 5 minutes**

Set up monitoring to detect issues early.

### Step 1: Configure Logging

Logs are automatically collected from functions:

```bash
# View function logs
vastde functions logs exr-inspector --tail 100

# View pipeline logs
vastde pipelines logs exr-inspect-pipeline --tail 100

# Filter for errors
vastde functions logs exr-inspector | grep -i error

# Export logs for analysis
vastde functions logs exr-inspector > exr-inspector-logs-$(date +%Y%m%d).txt
```

### Step 2: Set Up Alerts

Configure VAST alerts for critical issues:

```bash
# Create alert for function errors
vastde alerts create \
    --name "exr-inspector-errors" \
    --condition "function_status == FAILED" \
    --notify "ops-team@example.com"

# Create alert for slow pipeline runs
vastde alerts create \
    --name "exr-pipeline-slow" \
    --condition "pipeline_duration > 300" \
    --notify "ops-team@example.com"

# Create alert for database errors
vastde alerts create \
    --name "exr-database-connection" \
    --condition "persistence_status == ERROR" \
    --notify "ops-team@example.com"
```

### Step 3: Monitor Database Metrics

Track database health:

```bash
python3 << 'EOF'
import os
from vastdb_sdk import Session

session = Session(
    endpoint=os.getenv("VAST_DB_ENDPOINT"),
    access_key_id=os.getenv("VAST_DB_ACCESS_KEY"),
    secret_access_key=os.getenv("VAST_DB_SECRET_KEY"),
    region=os.getenv("VAST_DB_REGION", "us-east-1"),
    use_ssl=True,
)

bucket = session.get_bucket("exr-metadata-prod")
schema = bucket.get_schema("exr_metadata")

# Monitor row counts
files_table = schema.get_table("files")
parts_table = schema.get_table("parts")
channels_table = schema.get_table("channels")

file_count = files_table.count()
part_count = parts_table.count()
channel_count = channels_table.count()

print(f"Database metrics:")
print(f"  Files: {file_count}")
print(f"  Parts: {part_count}")
print(f"  Channels: {channel_count}")
print(f"  Average channels per file: {channel_count / max(file_count, 1):.1f}")

# Alert thresholds
if file_count > 1000000:
    print("  ⚠ WARNING: Over 1M files - consider partitioning")
if part_count > 5000000:
    print("  ⚠ WARNING: Over 5M parts - performance may degrade")
EOF
```

### Step 4: Create Dashboard

Create a monitoring dashboard to track:
- Files processed per hour
- Average function execution time
- Database query latency
- Error rate percentage
- Vector embedding computation time

Example Prometheus metrics export:

```bash
vastde metrics export exr-inspect-pipeline --format prometheus
```

---

## Rollback Procedures

**Critical**: Keep rollback procedures documented and tested.

### When to Rollback

Rollback if you observe:
- Persistent errors in function logs (>10% failure rate)
- Database connection failures after 15+ minutes
- Corrupted data in tables (verify with queries)
- Performance degradation (>2x slower than baseline)

### Rollback Scenario A: Function Code Issues

If the deployed code has bugs:

```bash
# Step 1: Stop the pipeline immediately
vastde pipelines stop exr-inspect-pipeline

# Step 2: Verify function is stopped
vastde functions describe exr-inspector
# Should show: Status = Stopped

# Step 3: Redeploy previous version
docker pull docker.io/your-org/exr-inspector:v0.9.0
docker tag docker.io/your-org/exr-inspector:v0.9.0 exr-inspector:v0.9.0

# Step 4: Update function in VAST
vastde functions update exr-inspector \
    --image docker.io/your-org/exr-inspector:v0.9.0 \
    --version v0.9.0

# Step 5: Verify deployment
vastde functions logs exr-inspector --tail 10
# Should show no errors

# Step 6: Restart pipeline
vastde pipelines start exr-inspect-pipeline

# Step 7: Confirm functionality
# Upload test file and verify processing
```

### Rollback Scenario B: Database Issues

If the database schema or data is corrupted:

```bash
# Step 1: Stop the pipeline
vastde pipelines stop exr-inspect-pipeline

# Step 2: Back up current schema
python3 << 'EOF'
import os
from vastdb_sdk import Session

session = Session(...)  # Connect with credentials
bucket = session.get_bucket("exr-metadata-prod")

# Export all tables to Parquet for backup
session.execute("""
    COPY (SELECT * FROM exr_metadata.files)
    TO PARQUET 's3://backups/files_backup_2025-02-06.parquet'
""")

# Similarly for parts, channels, attributes
EOF

# Step 3: Drop corrupted schema
python3 << 'EOF'
import os
from vastdb_sdk import Session

session = Session(...)
bucket = session.get_bucket("exr-metadata-prod")

# Drop schema (will delete all tables)
bucket.drop_schema("exr_metadata")
print("✓ Schema dropped")
EOF

# Step 4: Recreate schema (use Phase 1 script)
source .env.prod
python3 scripts/create_schema_prod.py

# Step 5: Restart pipeline
vastde pipelines start exr-inspect-pipeline
```

### Testing Rollback in Staging

Before executing rollback in production:

```bash
# Create staging copy of schema
vastde schema clone \
    --source exr_metadata \
    --target exr_metadata_staging_rollback_test

# Run rollback procedure on staging
source .env.prod
VAST_DB_SCHEMA="exr_metadata_staging_rollback_test" python3 scripts/create_schema_prod.py

# Verify staging rollback works
python3 << 'EOF'
# Connect to exr_metadata_staging_rollback_test
# Run queries to verify it's working
EOF
```

---

## Production Checklist

### Pre-Deployment

- [ ] All prerequisites verified (cluster, CLI, Docker, registry access)
- [ ] Team members notified of deployment window
- [ ] Staging environment tested (optional)
- [ ] Rollback procedure documented and tested
- [ ] All credentials securely stored
- [ ] Backup procedures defined

### Deployment Execution

- [ ] Phase 1: Schema and database setup completed
- [ ] Phase 2: Container built and pushed to registry
- [ ] Phase 3: Function deployed to VAST DataEngine
- [ ] Phase 4: Pipeline and triggers configured
- [ ] Phase 5: Smoke tests passed (all checks marked)

### Post-Deployment

- [ ] Monitoring and alerts configured
- [ ] First production file successfully processed
- [ ] Database verified with data
- [ ] Logs reviewed for errors
- [ ] Team notified of successful deployment
- [ ] Runbooks updated with any issues encountered

### Success Criteria

Before declaring deployment complete:

- **Schema**: 4 tables present, 0 rows initially
- **Function**: Status = "Ready", version v1.0.0
- **Logs**: No error messages in past 30 minutes
- **Database**: At least 1 file persisted after test
- **Embeddings**: 384D vectors present in metadata_embedding column
- **Alerts**: All monitoring rules active
- **Documentation**: PROD_RUNBOOK.md updated with specific endpoints/credentials

---

## Appendix: Common Issues & Solutions

### Issue: "Docker image not found in registry"

**Solution:**
```bash
# Verify image was pushed
docker push docker.io/your-org/exr-inspector:v1.0.0

# Check registry for image
docker pull docker.io/your-org/exr-inspector:v1.0.0

# In VAST UI, verify "Full Image Path" matches exactly
# docker.io/your-org/exr-inspector:v1.0.0
```

### Issue: "Function times out during execution"

**Possible causes:**
- VAST DataBase endpoint unreachable
- Large EXR files taking too long to process
- Network latency between VAST cluster and DataBase

**Solutions:**
```bash
# Increase function timeout (if supported)
vastde functions set-timeout exr-inspector --timeout 300

# Verify network connectivity
ping -c 5 s3.region.vastdata.com

# Check database performance
# See PROD_RUNBOOK.md Monitoring section
```

### Issue: "Persistence layer reports 'No session created'"

**Solution:**
```bash
# Verify environment variables are set
vastde functions describe exr-inspector
# Should show VAST_DB_ENDPOINT, VAST_DB_ACCESS_KEY, etc.

# Re-set if missing
vastde functions set-env exr-inspector \
    --env VAST_DB_ENDPOINT="s3.region.vastdata.com" \
    --env VAST_DB_ACCESS_KEY="<key>" \
    --env VAST_DB_SECRET_KEY="<secret>"
```

### Issue: "S3 trigger not firing"

**Solutions:**
1. Verify file matches trigger filter (.exr suffix)
2. Check S3 credentials in trigger configuration
3. Verify prefix matches (if specified)
4. Test trigger manually via VAST UI

---

## Related Documentation

- **Development guide**: [DEV_RUNBOOK.md](DEV_RUNBOOK.md)
- **Troubleshooting**: [TROUBLESHOOTING.md](TROUBLESHOOTING.md)
- **Vector embeddings**: [VECTOR_STRATEGY.md](VECTOR_STRATEGY.md)
- **Schema details**: [QUICK_START_VAST.md](QUICK_START_VAST.md)

---

**Last Updated:** February 2025

**Version:** 1.0.0+

**Target Audience:** DevOps/SRE teams, production operators

**Maintenance:** Review and update quarterly or after major VAST cluster upgrades
