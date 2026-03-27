# Architecture

## Overview

exr-inspector is a stateless serverless function that runs on VAST DataEngine. It processes OpenEXR files as they are ingested into a VAST S3 bucket, extracting structural metadata without reading pixel data.

## Event Flow

```
                    VAST S3 Bucket
                         |
                    [.exr uploaded]
                         |
                         v
              DataEngine Element Trigger
            (ElementCreated, suffix: .exr)
                         |
                    [CloudEvent]
                         |
                         v
               exr-inspector container
              +-------------------------+
              |  init(ctx)              |
              |    - Create S3 client   |
              |    - Validate OIIO      |
              +-------------------------+
              |  handler(ctx, event)    |
              |    1. Parse VastEvent   |
              |    2. Extract bucket/key|
              |    3. Download via S3   |
              |    4. Inspect EXR       |
              |    5. Persist to DB     |
              |    6. Cleanup temp file |
              +-------------------------+
                    |            |
                    v            v
              VAST S3       VAST DataBase
            (download)    (4 tables, vectors)
```

## Handler Lifecycle

### `init(ctx)` -- Container Startup

Called once when the container starts. Creates a global `boto3` S3 client from environment variables. This client is reused for all subsequent requests.

```python
s3_client = boto3.client(
    "s3",
    endpoint_url=os.environ["S3_ENDPOINT"],
    aws_access_key_id=os.environ["S3_ACCESS_KEY"],
    aws_secret_access_key=os.environ["S3_SECRET_KEY"],
)
```

### `handler(ctx, event)` -- Per-Request Processing

1. **Parse event** -- Receives a `VastEvent` object. For Element triggers, calls `event.as_element_event()` to extract `bucket` and `object_key` from the `elementpath` extension.

2. **Validate extension** -- Checks `.exr` suffix (case-insensitive). Non-EXR files return early.

3. **Download** -- Downloads the EXR file from S3 to ephemeral storage using the global `s3_client`.

4. **Inspect** -- Opens the file with OpenImageIO (`oiio.ImageInput.open()`). Iterates through all subimages, extracting parts, channels, and attributes. No pixel data is read.

5. **Persist** -- Computes deterministic vector embeddings, converts to PyArrow tables, and inserts into VAST DataBase. Tables are auto-created on first run.

6. **Cleanup** -- Deletes the temporary file in a `finally` block.

## Event Model

VAST DataEngine wraps events in `VastEvent` objects (not raw S3 notification dicts):

```python
# Element events (file operations)
if event.type == "Element":
    element_event = event.as_element_event()
    bucket = element_event.bucket          # From elementpath
    key = element_event.object_key         # From elementpath

# Fallback for other event types
event_data = event.get_data()
bucket = event_data.get("s3_bucket")
key = event_data.get("s3_key")
```

The `elementpath` extension contains the full S3 path (e.g., `my-bucket/renders/beauty.0001.exr`), which the runtime splits into bucket and key.

## EXR Inspection

OpenImageIO parses EXR headers without decompressing pixel data:

```
ImageInput.open(path)
  --> spec = input.spec()           # Get ImageSpec for current subimage
  --> spec.channelnames             # Channel names (AOVs)
  --> spec.channelformats           # Per-channel data types
  --> spec.extra_attribs            # All header attributes
  --> input.seek_subimage(n, 0)     # Move to next subimage
```

Complex OIIO types (vectors, matrices, bounding boxes, chromaticities) are serialized to JSON-compatible formats. Binary data is base64-encoded.

## Persistence

The persistence layer:

1. **Auto-provisions** schema and tables on first run (DDL in separate transaction)
2. **Computes embeddings** -- 384D metadata embedding + 128D channel fingerprint (deterministic, no ML)
3. **Converts to PyArrow** -- One PyArrow table per database table
4. **Inserts in transaction** -- files first, then parts/channels/attributes

Credentials fall back through: `VAST_DB_ENDPOINT` -> `S3_ENDPOINT`, `VAST_DB_ACCESS_KEY` -> `S3_ACCESS_KEY`.

## Design Decisions

| Decision | Rationale |
|----------|-----------|
| **Headers only, no pixels** | Keeps function fast (<5s per file). Pixel stats deferred to future version. |
| **Global S3 client** | Matches VAST DataEngine best practice. Created once in `init()`, reused per-request. |
| **Environment variables for credentials** | Consistent with working DataEngine functions. Set in pipeline config. |
| **Deterministic embeddings** | No ML model dependency in the container. SHA256-based expansion to target dimensions. |
| **Auto-provisioning tables** | Function is self-contained. No manual schema setup required. |
| **Denormalized file_path** | Avoids JOINs for common queries. Small storage trade-off for query performance. |
| **LD_LIBRARY_PATH Dockerfile.fix** | CNB buildpack exec.d mechanism doesn't set library paths correctly on all platforms. |
