# exr-inspector Function

VAST DataEngine serverless function for OpenEXR metadata extraction.

## Files

| File | Purpose |
|------|---------|
| `main.py` | Handler: event parsing, S3 download, EXR inspection |
| `vast_db_persistence.py` | VAST DataBase persistence, vector embeddings, table auto-creation |
| `requirements.txt` | Python dependencies (boto3, pyarrow, vastdb) |
| `Aptfile` | System packages (libopenimageio-dev, libopenexr-dev) |

## Handler Signature

```python
def init(ctx):    # One-time setup: create S3 client from env vars
def handler(ctx, event):  # Per-request: download, inspect, persist
```

## Build

```bash
vastde functions build exr-inspector --target functions/exr_inspector --pull-policy never
```

## Test

```bash
pytest test_vast_db_persistence.py -v
```

See [Deployment Guide](../../docs/DEPLOYMENT.md) for full instructions.
