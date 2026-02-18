# exr-inspector: Automated Deployment Guide

**Automated deployment of exr-inspector to VAST DataEngine with DataBase integration**

This guide shows you how to use the automated `deploy.sh` script to deploy exr-inspector with minimal manual steps. The script handles credential management, container building, registry pushing, and deployment verification.

---

## Quick Start (3 Steps)

### Step 1: Prepare Configuration

```bash
cd /Users/sergio.soto/Development/ai-apps/code/exr-inspector/git

# Copy configuration template
cp .env.example .env

# Edit with your VAST cluster details
# Required:
#   - VAST_CLUSTER_URL (https://your-cluster)
#   - VAST_API_KEY (from VAST admin)
#   - VAST_DB_ENDPOINT (s3.region.vastdata.com)
#   - VAST_DB_ACCESS_KEY
#   - VAST_DB_SECRET_KEY
#   - REGISTRY_URL (docker.io or your registry)
#   - REGISTRY_USERNAME
#   - REGISTRY_PASSWORD
nano .env
```

### Step 2: Run Deployment Script

```bash
# Interactive mode (prompts for missing values)
./deploy.sh

# Or with config file
./deploy.sh --config .env

# Or load from environment
source .env && ./deploy.sh
```

### Step 3: Complete Manual VAST UI Steps

Script will output next steps (schema creation, function setup, trigger configuration). Follow the generated JSON files for manual VAST UI setup.

---

## How It Works

### Deployment Phases

The script automates 5 deployment phases:

```
Phase 1: Schema & Database Setup (15 min)
  ├── Generates VAST DataBase schema SQL
  ├── Creates 4 tables: files, parts, channels, attributes
  └── Creates performance indexes

Phase 2: Build & Container Registry (15 min)
  ├── Builds Docker image with vastde CLI
  ├── Authenticates with container registry
  └── Pushes image to registry

Phase 3: Function Deployment (10 min)
  ├── Generates VAST function configuration
  ├── Sets environment variables (VAST_DB_*)
  └── Creates function in VAST UI (manual)

Phase 4: Trigger & Pipeline (10 min)
  ├── Generates trigger configuration
  ├── Creates pipeline with S3 bucket trigger
  └── Deploys pipeline (manual)

Phase 5: Verification & Smoke Tests (10 min)
  ├── Runs 45+ unit tests locally
  ├── Validates vector embeddings
  └── Outputs test event template

Post-Deployment:
  └── Monitors logs and verifies data persistence
```

---

## Usage Modes

### Mode 1: Interactive (No Config File)

Run script and answer prompts:

```bash
./deploy.sh

# Script will prompt for:
# - VAST cluster URL
# - API key
# - DataBase endpoint & credentials
# - Registry details
# - S3 bucket name
```

**Best for:** First-time deployments, single-use setups

### Mode 2: Configuration File (Recommended for Teams)

```bash
# Create .env file with all details
cp .env.example .env
# ... edit .env ...

# Run deployment
./deploy.sh --config .env
```

**Best for:** Team deployments, CI/CD integration, repeatable deployments

### Mode 3: Environment Variables

```bash
# Set env vars in shell
export VAST_CLUSTER_URL="https://..."
export VAST_API_KEY="..."
# ... set other vars ...

# Run deployment
./deploy.sh
```

**Best for:** Container environments, CI/CD pipelines

---

## Configuration Details

### Required Variables

```bash
# VAST Cluster (where functions run)
VAST_CLUSTER_URL          # URL to VAST cluster
VAST_API_KEY              # API key for authentication
VAST_TENANT_NAME          # Tenant name (usually "default")

# VAST DataBase (where metadata persists)
VAST_DB_ENDPOINT          # S3 endpoint for DataBase
VAST_DB_ACCESS_KEY        # AWS-style access key
VAST_DB_SECRET_KEY        # AWS-style secret key
VAST_DB_REGION            # AWS region (us-east-1, etc.)
VAST_DB_SCHEMA            # Schema name (exr_metadata)

# Container Registry (where image is stored)
REGISTRY_URL              # Registry hostname
REGISTRY_USERNAME         # Registry authentication
REGISTRY_PASSWORD         # Registry authentication

# Image Details
IMAGE_REPOSITORY          # Org/image name
IMAGE_TAG                 # Version tag

# S3 Input
S3_BUCKET                 # Bucket with EXR files
```

### Optional Variables

```bash
VAST_DB_REGION            # Default: us-east-1
VAST_DB_SCHEMA            # Default: exr_metadata
IMAGE_TAG                 # Default: v1.0.0
FUNCTION_TIMEOUT          # Default: 300 seconds
FUNCTION_MEMORY           # Default: 1024 MB
```

---

## What the Script Does

### Phase 1: Schema & Database Setup

**Generated File:** `/tmp/exr_schema.sql`

Creates 4 normalized tables:

```sql
CREATE TABLE exr_metadata.files (
  file_id STRING PRIMARY KEY,
  file_path_normalized STRING,
  header_hash STRING,
  metadata_embedding FLOAT VECTOR(384),  -- 384D embeddings
  ...
  UNIQUE (file_path_normalized, header_hash)
);

CREATE TABLE exr_metadata.parts (
  part_id STRING PRIMARY KEY,
  file_id STRING REFERENCES files(file_id),
  ...
);

CREATE TABLE exr_metadata.channels (
  channel_id STRING PRIMARY KEY,
  channel_fingerprint FLOAT VECTOR(128),  -- 128D fingerprints
  ...
);

CREATE TABLE exr_metadata.attributes (
  attribute_id STRING PRIMARY KEY,
  ...
);
```

**To Apply Schema:**
```bash
# Option 1: VAST Web UI
# Navigate to Query Editor, paste contents of /tmp/exr_schema.sql

# Option 2: VAST CLI
vastdb query < /tmp/exr_schema.sql

# Option 3: ADBC Client
python3 -c "
import adbc_driver_manager
with adbc_driver_manager.connect(...) as conn:
    with open('/tmp/exr_schema.sql') as f:
        conn.execute(f.read())
"
```

### Phase 2: Build & Container Registry

**Performs:**
1. Builds Docker image: `docker build -t IMAGE:TAG functions/exr_inspector/`
2. Authenticates with registry: `docker login`
3. Pushes to registry: `docker push REGISTRY/IMAGE:TAG`

**Automatic Retry:** 3 attempts on failure

**Generated Config:** None (uses existing Dockerfile)

### Phase 3: Function Deployment

**Generated File:** `/tmp/exr_function.json`

```json
{
  "name": "exr-inspector",
  "image": "docker.io/my-org/exr-inspector:v1.0.0",
  "environmentVariables": {
    "VAST_DB_ENDPOINT": "s3.region.vastdata.com",
    "VAST_DB_ACCESS_KEY": "***",
    "VAST_DB_SECRET_KEY": "***",
    "VAST_DB_REGION": "us-east-1",
    "VAST_DB_SCHEMA": "exr_metadata"
  }
}
```

**Manual Steps:**
1. Log into VAST Web UI
2. Navigate to: **Manage Elements → Functions**
3. Click: **Create New Function**
4. Fill in: Name, Description, Container Image, Registry, Image Tag, Environment Variables

### Phase 4: Trigger & Pipeline

**Generated File:** `/tmp/trigger_config.json`

**Manual Steps:**
1. Create Trigger: Element trigger on S3 bucket for `.exr` files
2. Create Pipeline: Connect trigger → exr-inspector function
3. Deploy: Start pipeline

### Phase 5: Verification & Smoke Tests

**Runs:**
```bash
pytest functions/exr_inspector/test_vast_db_persistence.py -v

# Expected: 45+ tests pass
# Time: ~5-10 seconds
# No VAST cluster required
```

---

## Error Handling & Recovery

### Build Failures

If Docker build fails:

```bash
# Check Docker daemon
docker ps

# Rebuild with verbose output
docker build -t IMAGE:TAG --verbose functions/exr_inspector/

# Check for base image issues
docker pull python:3.10-slim
```

### Registry Push Failures

```bash
# Verify registry access
docker pull REGISTRY/test:latest

# Re-authenticate
docker logout REGISTRY
docker login REGISTRY

# Try push again
docker push REGISTRY/IMAGE:TAG
```

### VAST Cluster Connection Issues

```bash
# Test cluster connectivity
curl -k https://VAST_CLUSTER_URL/api/system/info

# Verify API key
curl -H "Authorization: Bearer $VAST_API_KEY" \
     https://VAST_CLUSTER_URL/api/system/info

# Check vastde CLI config
vastde cluster list
vastde cluster current
```

### Schema Creation Issues

See `/tmp/exr_schema.sql` for SQL to manually execute.

```bash
# Verify table creation
vastdb query "SELECT * FROM exr_metadata.files LIMIT 1"

# Check for existing tables
vastdb query "SHOW TABLES IN exr_metadata"

# View schema
vastdb query "DESCRIBE exr_metadata.files"
```

---

## Logging & Debugging

### Deployment Log

All output is logged to:
```
./deployment.log
```

View in real-time:
```bash
tail -f deployment.log
```

### Configuration Saved

Configuration is saved to:
```
./.deployment.state
```

Load previous config:
```bash
source .deployment.state
./deploy.sh
```

### Verbose Output

```bash
# Run with debug output
DEBUG=true ./deploy.sh

# Tail logs continuously
tail -f deployment.log
```

---

## Post-Deployment Testing

### Upload Test File

```bash
# Create minimal test EXR or use existing
aws s3 cp test.exr s3://exr-input-data/

# Monitor function execution
vastde pipelines logs -f exr-inspector
```

### Query Results

```bash
# Check if file was indexed
vastdb query "SELECT file_path, inspection_count FROM exr_metadata.files"

# Count indexed files
vastdb query "SELECT COUNT(*) as total_files FROM exr_metadata.files"

# Find files with vector embeddings
vastdb query "
SELECT file_path, array_length(metadata_embedding) as embedding_dims
FROM exr_metadata.files
WHERE metadata_embedding IS NOT NULL
LIMIT 10
"

# Check channel statistics
vastdb query "
SELECT COUNT(*) as total_channels,
       COUNT(DISTINCT layer_name) as unique_layers
FROM exr_metadata.channels
"
```

### Analytics Queries

See `docs/VAST_ANALYTICS_QUERIES.md` for example queries:
- Find similar renders (vector similarity)
- Detect anomalies (unusual metadata)
- Channel composition analysis
- Deep EXR detection
- Compression statistics

---

## Rollback & Recovery

### Rollback Function Code

If deployed version has issues:

```bash
# Rebuild previous version
docker pull registry/exr-inspector:v0.9.0

# Redeploy to VAST
vastde functions build exr-inspector \
  --image-tag registry/exr-inspector:v0.9.0

# Wait for deployment to complete
vastde functions status exr-inspector
```

### Rollback Database (if needed)

```bash
# Backup current data
vastdb query "
CREATE TABLE exr_metadata.files_backup AS
SELECT * FROM exr_metadata.files
"

# Clear tables if needed
TRUNCATE TABLE exr_metadata.files;
TRUNCATE TABLE exr_metadata.parts;
TRUNCATE TABLE exr_metadata.channels;
TRUNCATE TABLE exr_metadata.attributes;
```

### Full Cleanup

```bash
# Drop entire schema
vastdb query "DROP SCHEMA exr_metadata CASCADE"

# Delete container image
docker rmi registry/exr-inspector:v1.0.0

# Delete function from VAST
vastde functions delete exr-inspector
```

---

## Common Issues & Solutions

### Issue: "Registry authentication failed"

**Solution:**
```bash
# Verify credentials
echo $REGISTRY_PASSWORD | docker login -u $REGISTRY_USERNAME REGISTRY_URL

# Check registry URL format
# Should be: docker.io, ghcr.io, ecr.us-east-1.amazonaws.com, etc.
```

### Issue: "VAST cluster not accessible"

**Solution:**
```bash
# Test connectivity
ping VAST_CLUSTER_URL
curl -k https://VAST_CLUSTER_URL/

# Verify firewall allows 443/8089
telnet VAST_CLUSTER_URL 443

# Check API key validity
vastde cluster info --endpoint VAST_CLUSTER_URL --key $VAST_API_KEY
```

### Issue: "Container build failed"

**Solution:**
```bash
# Check Docker daemon
docker version

# Rebuild with verbose output
docker build -t IMAGE:TAG --progress=plain functions/exr_inspector/

# Check for missing dependencies
ls functions/exr_inspector/requirements.txt
```

### Issue: "Database connection timeout"

**Solution:**
```bash
# Test endpoint connectivity
curl https://VAST_DB_ENDPOINT

# Verify credentials work
aws s3 ls --endpoint-url https://VAST_DB_ENDPOINT \
  --profile vast

# Check firewall/network rules
telnet VAST_DB_ENDPOINT 443
```

---

## Next Steps After Deployment

1. **Monitor Logs**
   ```bash
   vastde pipelines logs -f exr-inspector
   ```

2. **Upload Test Files**
   ```bash
   aws s3 cp sample.exr s3://exr-input-data/
   ```

3. **Verify Data**
   ```bash
   vastdb query "SELECT * FROM exr_metadata.files LIMIT 5"
   ```

4. **Run Analytics**
   See `docs/VAST_ANALYTICS_QUERIES.md` for SQL examples

5. **Set Up Monitoring**
   See `docs/PROD_RUNBOOK.md` for alerting setup

---

## Support & Troubleshooting

### Detailed Documentation

- **Development**: `docs/DEV_RUNBOOK.md` (local testing)
- **Production**: `docs/PROD_RUNBOOK.md` (manual deployment)
- **Troubleshooting**: `docs/TROUBLESHOOTING.md` (30+ solutions)
- **Analytics**: `docs/VAST_ANALYTICS_QUERIES.md` (SQL examples)

### Script Troubleshooting

```bash
# Check script syntax
bash -n deploy.sh

# Run with bash debug
bash -x deploy.sh

# Check permissions
ls -la deploy.sh
# Should be: -rwxr-xr-x
```

### Configuration Issues

```bash
# Validate .env file syntax
bash -n .env

# Source and check variables
source .env
echo "VAST_CLUSTER_URL=$VAST_CLUSTER_URL"
echo "REGISTRY_URL=$REGISTRY_URL"
# (don't echo secrets)
```

---

## Summary

The automated deployment script (`deploy.sh`) streamlines exr-inspector deployment to VAST DataEngine:

✅ **Automated:** 5 deployment phases, error handling, retry logic
✅ **Secure:** Prompts for secrets (doesn't store in history), env var support
✅ **Flexible:** Interactive mode, config file, environment variables
✅ **Tested:** Runs 45+ unit tests to verify code
✅ **Observable:** Detailed logging, generated configs, next-step guidance
✅ **Recoverable:** Configuration saved, rollback procedures documented

**Total Deployment Time:** 60-90 minutes (first time), 20-30 minutes (updates)

**Getting Started:**
```bash
cd /Users/sergio.soto/Development/ai-apps/code/exr-inspector/git
cp .env.example .env
# Edit .env with VAST cluster details
./deploy.sh --config .env
```
