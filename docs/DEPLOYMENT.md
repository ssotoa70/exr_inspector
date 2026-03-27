# Deployment Guide

This guide covers building, deploying, and configuring exr-inspector on VAST DataEngine.

## Prerequisites

- **vastde CLI** v5.4.1+ installed and configured
- **Docker** running with `"min-api-version": "1.38"` in daemon config
- **VAST Cluster** 5.4+ with DataEngine enabled
- **Container registry** connected to your DataEngine tenant
- **S3 bucket** (source view) for EXR file ingestion
- **Database-enabled bucket** for VAST DataBase persistence

## Step 1: Configure vastde CLI

```bash
vastde config init \
  --vms-url $VMS_URL \
  --tenant $TENANT_NAME \
  --username $USERNAME \
  --password $PASSWORD \
  --builder-image-url $BUILDER_IMAGE_URL
```

Verify configuration:

```bash
vastde config view
vastde functions list
vastde buckets list
```

## Step 2: Build the Function Image

```bash
# From the repository root
vastde functions build exr-inspector \
  --target functions/exr_inspector \
  --pull-policy never
```

The build uses Cloud Native Buildpacks (CNB) to create a container image with:
- Python 3.12 runtime
- OpenImageIO + OpenEXR system libraries (via Aptfile)
- boto3, pyarrow, vastdb Python dependencies
- VAST runtime SDK

### Apply LD_LIBRARY_PATH Fix

CNB buildpack images require an additional layer to set library paths correctly:

```bash
docker build --platform linux/amd64 --no-cache \
  -t $REGISTRY_HOST/exr-inspector:latest \
  -f Dockerfile.fix .
```

## Step 3: Push to Container Registry

```bash
docker push $REGISTRY_HOST/exr-inspector:latest
```

## Step 4: Create the Function

### Via vastde CLI

```bash
vastde functions create \
  --name exr-inspector \
  --description "EXR metadata extraction with VAST DataBase persistence" \
  --container-registry $REGISTRY_NAME \
  --artifact-source exr-inspector \
  --image-tag latest
```

### Via VMS UI

1. Navigate to **Manage Elements** -> **Functions** -> **Create New Function**
2. Fill in:
   - **Name:** `exr-inspector`
   - **Container Registry:** Select your registry
   - **Artifact Source:** `exr-inspector`
   - **Image Tag:** `latest`
3. Ensure **"Make local revision"** is **unchecked**
4. Click **Create**

## Step 5: Create the Element Trigger

```bash
vastde triggers create \
  --type Element \
  --name exr-trigger \
  --description "Watch for new EXR files" \
  --source-bucket $SOURCE_BUCKET \
  --events "ObjectCreated:*" \
  --name-suffix ".exr"
```

## Step 6: Create and Deploy the Pipeline

### Via VMS UI (Recommended)

1. **Manage Elements** -> **Pipelines** -> **Create New Pipeline**
2. **Name:** `exr-inspector-pipeline`
3. **Add environment variables** (see [Configuration](CONFIGURATION.md)):

   | Variable | Value |
   |----------|-------|
   | `S3_ENDPOINT` | `http://$DATA_VIP` |
   | `S3_ACCESS_KEY` | `$S3_ACCESS_KEY` |
   | `S3_SECRET_KEY` | `$S3_SECRET_KEY` |
   | `VAST_DB_BUCKET` | `$DATABASE_BUCKET` |
   | `VAST_DB_SCHEMA` | `exr_metadata` |

4. **Add function deployment:** Select `exr-inspector`
5. **Link trigger:** Connect `exr-trigger` -> `exr-inspector`
6. Click **Create Pipeline**
7. **Deploy** the pipeline

## Step 7: Verify Deployment

```bash
# Check pipeline status
vastde pipelines list

# Tail logs
vastde logs tail exr-inspector-pipeline

# Check function status
vastde functions get exr-inspector -o json
```

## Step 8: Test

Upload a test EXR file to the source bucket:

```bash
aws s3 cp sample.exr s3://$SOURCE_BUCKET/ \
  --endpoint-url http://$DATA_VIP
```

Monitor the logs:

```bash
vastde logs get exr-inspector-pipeline --since 5m
```

## Updating the Function

After code changes:

```bash
# 1. Rebuild
vastde functions build exr-inspector --target functions/exr_inspector --pull-policy never

# 2. Apply LD_LIBRARY_PATH fix
docker build --platform linux/amd64 --no-cache \
  -t $REGISTRY_HOST/exr-inspector:latest -f Dockerfile.fix .

# 3. Push
docker push $REGISTRY_HOST/exr-inspector:latest

# 4. Update function revision (via CLI or VMS UI)
vastde functions update exr-inspector --image-tag latest

# 5. Redeploy pipeline
vastde pipelines deploy exr-inspector-pipeline
```

## Docker Configuration Note

The `vastde` CLI embeds a Docker client that requires API version 1.38. Modern Docker Desktop (v4.40+) defaults to a minimum of 1.40. Add this to your Docker Engine configuration:

```json
{
  "min-api-version": "1.38"
}
```

In Docker Desktop: **Settings** -> **Docker Engine** -> edit JSON -> **Apply & restart**.
