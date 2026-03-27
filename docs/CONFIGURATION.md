# Configuration Reference

All configuration is via environment variables, set in the DataEngine pipeline or function deployment config.

## Required Environment Variables

### S3 Access (Source Bucket)

| Variable | Description | Example |
|----------|-------------|---------|
| `S3_ENDPOINT` | VAST S3 data VIP endpoint | `http://$DATA_VIP` |
| `S3_ACCESS_KEY` | S3 access key for source bucket | `$ACCESS_KEY` |
| `S3_SECRET_KEY` | S3 secret key for source bucket | `$SECRET_KEY` |

These credentials are used to download EXR files from the S3 bucket. The S3 client is created once in `init()` and reused for all requests.

### VAST DataBase Persistence

| Variable | Description | Default |
|----------|-------------|---------|
| `VAST_DB_ENDPOINT` | VAST DataBase endpoint | Falls back to `S3_ENDPOINT` |
| `VAST_DB_ACCESS_KEY` | DataBase access key | Falls back to `S3_ACCESS_KEY` |
| `VAST_DB_SECRET_KEY` | DataBase secret key | Falls back to `S3_SECRET_KEY` |
| `VAST_DB_BUCKET` | Database-enabled bucket name | `$DATABASE_BUCKET` |
| `VAST_DB_SCHEMA` | Schema name for metadata tables | `exr_metadata` |

If `VAST_DB_ENDPOINT` is not set, the function falls back to `S3_ENDPOINT`. This works when both S3 and DataBase are accessible via the same VIP.

## Pipeline Configuration

### Via VMS UI

When creating or editing a pipeline, add environment variables in the **Environment Variables** section:

```
S3_ENDPOINT      = http://$DATA_VIP
S3_ACCESS_KEY    = $ACCESS_KEY
S3_SECRET_KEY    = $SECRET_KEY
VAST_DB_BUCKET   = $DATABASE_BUCKET
VAST_DB_SCHEMA   = exr_metadata
```

### Via config.yaml (Local Testing)

```yaml
envs:
  S3_ENDPOINT: "http://$DATA_VIP"
  S3_ACCESS_KEY: "$ACCESS_KEY"
  S3_SECRET_KEY: "$SECRET_KEY"
  VAST_DB_BUCKET: "$DATABASE_BUCKET"
  VAST_DB_SCHEMA: "exr_metadata"
```

Use with `vastde functions localrun`:

```bash
vastde functions localrun exr-inspector --config config.yaml
```

## Trigger Configuration

The element trigger watches for new EXR files:

| Setting | Value |
|---------|-------|
| **Trigger Type** | Element |
| **Event Type** | ElementCreated (ObjectCreated:*) |
| **Source Type** | S3 |
| **Source Bucket** | Your S3 ingestion bucket |
| **Suffix Filter** | `.exr` |

## Credentials Security

- Credentials are loaded **once** during `init()`, never per-request
- Secret values are **masked** in init logs (first 4 and last 4 chars only)
- Events **never** contain credentials, only file locations
- Use **separate credentials** for S3 (read-only) and DataBase (write) in production
- Store credentials in pipeline environment variables (encrypted at rest by VAST)

## .env.example

For local development reference:

```bash
# S3 source bucket access
S3_ENDPOINT=http://$DATA_VIP
S3_ACCESS_KEY=$ACCESS_KEY
S3_SECRET_KEY=$SECRET_KEY

# VAST DataBase persistence (optional, falls back to S3_* vars)
# VAST_DB_ENDPOINT=http://$DB_VIP
# VAST_DB_ACCESS_KEY=$DB_ACCESS_KEY
# VAST_DB_SECRET_KEY=$DB_SECRET_KEY
VAST_DB_BUCKET=$DATABASE_BUCKET
VAST_DB_SCHEMA=exr_metadata
```
