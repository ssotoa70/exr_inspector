# Performance Optimization Plan

## Baseline (2026-04-02)

First live test with 500 EXR frames:
- **Throughput:** 2.3 files/second (~138 files/min)
- **Config:** Single pod, concurrency max=5, ordered delivery
- **Failure:** ConnectionResetError after ~35 files (vastdb session created per-event)
- **Target:** 5,000+ files/minute for production VFX pipelines

## Bottlenecks Identified

1. VastDB session created and destroyed per event (connection exhaustion)
2. `ensure_database_tables()` runs 5 DDL lookups per event (redundant after first run)
3. Ordered delivery serializes event processing
4. Single pod / low concurrency
5. Unnecessary S3 HEAD request (Range GET already returns file size)
6. INFO logging generates 75K log lines/min at scale
7. One transaction per file (not batched)

---

## P0 — Critical Path (Target: 3,000 files/min)

### P0.1: Move VastDB session to init()
- [ ] Create `vastdb_session` global in `init(ctx)`
- [ ] Reuse session across all handler invocations
- [ ] Pass as `vastdb_session=` to `persist_to_vast_database()`
- [ ] Fixes ConnectionResetError (root cause: TCP connection churn)

### P0.2: Move DDL to init()
- [ ] Call `ensure_database_tables()` once in `init(ctx)`
- [ ] Add `_tables_verified` flag to skip on subsequent invocations
- [ ] Skip DDL in `persist_to_vast_database()` when session is pre-initialized

### P0.3: Switch to unordered delivery
- [ ] Change pipeline Method of Delivery from `ordered` to `unordered` in VMS UI
- [ ] Enables concurrent event processing within each pod

---

## P1 — Scale Out (Target: 14,400 files/min)

### P1.1: Increase concurrency
- [ ] Set Min concurrency: 5
- [ ] Set Max concurrency: 20
- [ ] Configure in VMS UI pipeline deployment

### P1.2: Eliminate HEAD request
- [ ] Remove `s3_client.head_object()` call
- [ ] Extract full file size from Range GET `Content-Range` header
- [ ] Saves 1 HTTP round-trip per file (~5-10ms)

### P1.3: Set log level to WARNING
- [ ] Change log level in pipeline deployment config
- [ ] Reduces log volume from ~15 lines/file to ~1 line/file

### P1.4: Set RPS factor to 10
- [ ] Configure in VMS UI pipeline deployment
- [ ] Triggers faster pod scale-up under burst load

### P1.5: Tune boto3 connection pool
- [ ] Set `max_pool_connections=25` (default is 10)
- [ ] Add adaptive retry mode
- [ ] Add connect/read timeouts

---

## P2 — Batch Mode (Target: 24,000 files/min)

### P2.1: Batch inserts
- [ ] Accumulate metadata for 50 files in memory
- [ ] Flush as single transaction (pa.concat_tables)
- [ ] Add timeout-based flush (5 seconds max wait)
- [ ] Thread-safe with lock for concurrent pod invocations

### P2.2: Event Broker partition tuning
- [ ] Check current topic partition count
- [ ] Increase to 20 partitions if below (matches max pod count)
- [ ] May require new topic creation

---

## Expected Throughput

| Stage | Per Pod | Pods | Files/min | Status |
|-------|---------|------|-----------|--------|
| Baseline | 2.3/s | 1 | ~138 | Done |
| After P0 | 10/s | 5 | ~3,000 | |
| After P0+P1 | 12/s | 20 | ~14,400 | |
| After P0+P1+P2 | 20/s | 20 | ~24,000 | |

## Pod Resource Sizing (P1+)

| Resource | Min | Max |
|----------|-----|-----|
| CPU | 0.25 | 1.0 |
| Memory | 256Mi | 512Mi |
| Ephemeral Disk | 50Mi | 50Mi |
| Concurrency | 5 | 20 |
| RPS Factor | 10 | — |
| Timeout | 30s | — |
| Log Level | WARNING | — |
| Delivery | unordered | — |
