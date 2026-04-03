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
              |    3. Range GET header  |
              |       (256KB, not full) |
              |    4. Inspect EXR       |
              |    5. Persist to DB     |
              |    6. Cleanup temp file |
              +-------------------------+
                    |            |
                    v            v
              VAST S3       VAST DataBase
          (range GET)    (4 tables, vectors)
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

3. **Fetch header** -- Issues an S3 `HEAD` request for file size/mtime, then a **Range GET** (`bytes=0-262143`) to fetch only the first 256KB of the file. All EXR metadata lives in the header (typically 1-50KB). No pixel data is ever transferred.

4. **Inspect** -- Writes the 256KB header to a small temp file, then opens it with OpenImageIO (`oiio.ImageInput.open()`). Iterates through all subimages, extracting parts, channels, and attributes.

5. **Persist** -- Computes deterministic vector embeddings, converts to PyArrow tables, and inserts into VAST DataBase. Tables are auto-created on first run.

6. **Cleanup** -- Deletes the small temp file (~256KB) in a `finally` block.

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

1. **Auto-provisions** schema and tables on first run (DDL in `init()`, separate transaction)
2. **Idempotent upsert** -- SELECT by `file_id` before insert. If the file already exists, updates `last_inspected` and increments `inspection_count`. No duplicate rows on re-ingestion.
3. **Computes embeddings** -- 384D metadata embedding + 128D channel fingerprint (deterministic, no ML)
4. **Converts to PyArrow** -- One PyArrow table per database table
5. **Inserts in transaction** -- files first, then parts/channels/attributes

### Idempotency

The `file_id` is deterministic: `SHA256(path + mtime + header_hash)`.

| Scenario | Behavior |
|----------|----------|
| New file | SELECT finds nothing -> INSERT all 4 tables |
| Re-ingested (same content) | Same `file_id` -> UPDATE audit fields only |
| Re-ingested (modified content) | Different `header_hash` -> new `file_id` -> INSERT as new |

Credentials fall back through: `VAST_DB_ENDPOINT` -> `S3_ENDPOINT`, `VAST_DB_ACCESS_KEY` -> `S3_ACCESS_KEY`.

## Design Decisions

| Decision | Rationale |
|----------|-----------|
| **S3 Range GET (256KB header)** | Only fetches the EXR header, not the full file. Reduces ephemeral disk from ~2GB to ~256KB per pod. Enables 5,000+ concurrent files with minimal resources. |
| **Headers only, no pixels** | All metadata lives in the EXR header. No pixel data is ever transferred or decompressed. |
| **Global S3 client** | Matches VAST DataEngine best practice. Created once in `init()`, reused per-request. |
| **Environment variables for credentials** | Consistent with working DataEngine functions. Set in pipeline config. |
| **Deterministic embeddings** | No ML model dependency in the container. SHA256-based expansion to target dimensions. |
| **Idempotent upsert** | SELECT before INSERT prevents duplicates. Safe for re-ingestion. |
| **Auto-provisioning tables** | Function is self-contained. No manual schema setup required. |
| **Denormalized file_path** | Avoids JOINs for common queries. Small storage trade-off for query performance. |
| **LD_LIBRARY_PATH Dockerfile.fix** | CNB buildpack exec.d mechanism doesn't set library paths correctly on all platforms. |

## Scalability

The function is designed for high-throughput ingestion (thousands of files per minute):

| Metric | Per Pod | 100 Concurrent Pods |
|--------|---------|---------------------|
| S3 data transferred | ~256KB | ~25MB |
| Ephemeral disk | ~256KB | ~25MB |
| Processing time | <100ms | 5,000 files in ~30s |

Key scaling factors:
- **DataEngine/Knative** autoscales pods based on event backpressure
- **VAST Event Broker** durably queues events (Kafka-compatible, no data loss)
- **S3 Range GET** eliminates bandwidth and disk bottlenecks
- **VAST DataBase** handles concurrent inserts without row-level locking

Configure in the pipeline deployment:
- `Concurrency`: min=10, max=200
- `Method of Delivery`: unordered (critical for parallel processing)
- `Ephemeral Disk`: 512Mi (generous headroom for 256KB headers)
- `Timeout`: 300s
