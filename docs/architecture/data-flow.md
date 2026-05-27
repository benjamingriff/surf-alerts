# Data Flow

> **Status: IMPLEMENTED** (scrape + store) | **PLANNED** (layered storage + event-driven processing)

## Storage Boundary (Current Implementation And Planned Target)

The current implementation still writes gzip JSON to flat S3 keys via `{prefix}.gz`.
The diagram below shows the **target storage boundary** after the layered storage rework, where scraper writes land in `raw/` and downstream processors publish `processed/` and `control/` objects.

```
Surfline API
     │
     ▼
┌────────────────┐     SQS Message:
│  SQS Queue     │◄─── { spot_id, bucket, prefix }
│  (batch: 1)    │
└───────┬────────┘
        │
        ▼
┌────────────────┐     curl-cffi with Chrome impersonation
│  Lambda        │──── 3 retries, exponential backoff + jitter
│  (Docker)      │     30s timeout per HTTP request
└───────┬────────┘
        │
        ▼
┌────────────────┐
│  S3 Bucket     │     Raw write:
│  {stack}-data  │     raw/{source_type}/...
└───────┬────────┘
        │
        ▼
┌────────────────┐     S3 object created / manifest-driven trigger
│  Processor     │──── Transform raw payloads into Parquet + serving data
│  (planned)     │
└───────┬────────┘
        │
        ├──▶ processed/...      Version tables, serving snapshots, analytics
        └──▶ control/...        Manifests, checkpoints, completion records
```

### Forecast Flow

```
Hourly EventBridge tick (UTC)
     │
     └──▶ Forecast Run Planner
            ├── Reads: live processed spots for only the due UTC offset
            ├── Writes: DynamoDB Forecast Run + planned spot control items
            └── Enqueues: one forecast scrape per spot_id

Forecast scrape SQS
     │
     └──▶ Forecast Scraper
            ├── Fetches: rating, tides, wave, wind
            ├── Writes: raw/forecast/... only for successful scrapes
            └── Emits: terminal completion message

Forecast completion SQS
     │
     └──▶ Forecast Spot Processor
            ├── Records scrape terminal state in DynamoDB
            ├── Reads successful raw forecast object from S3
            ├── Transforms rating, wave, swells, wind, tides
            ├── Inserts Postgres fact rows in one transaction
            └── Updates DynamoDB processing/run rollup state
```

Key forecast rules:

- Forecast v1 uses DynamoDB for control state, not S3 manifests or completion marker objects.
- Weather and sunlight are intentionally excluded from collection and storage.
- Successful fact inserts target `forecast_fact_rating`, `forecast_fact_wave`, `forecast_fact_swells`, `forecast_fact_wind`, and `forecast_fact_tides`.

**Units requested:** `swellHeight=FT`, `waveHeight=FT`, `windSpeed=MPH`, `tideHeight=FT`.

### Spot Scraper Flow

1. SQS message arrives with `spot_id`, `bucket`, `prefix`
2. Lambda makes 1 HTTP request to `/kbyg/spots/reports?spotId={spot_id}`
3. Response written to `raw/spot_report/...`
4. A downstream processor canonicalizes it, computes a checksum, and appends new discovery versions when content changes

**Planned downstream outputs:**
- `processed/discovery/dim_spots_core/...` - append-only version anchor table
- `processed/discovery/dim_spot_*/...` - append-only child dimension tables
- `processed/discovery/events/...` - append-only `added`, `changed`, `removed` lifecycle events
- `processed/discovery/catalog_latest/...` - derived latest live catalog for operational reads

### Discovery Flow (Planned Target)

```
EventBridge Cron
     │
     └── 06:00 UTC ──▶ Sitemap Scraper ──▶ raw/sitemap/...
                                      │
                                      ▼
                           Discovery Diff Lambda
                           ├── Reads: raw sitemap + latest catalog
                           ├── Writes: processed/discovery/events/... (`added`, `removed`)
                           └── Enqueues: new spot IDs for spot scraper

SQS / S3 Event
     │
     └──▶ Spot Scraper ──▶ raw/spot_report/...
                              │
                              ▼
                     Spot Report Processor Lambda
                     ├── Canonicalizes spot payload
                     ├── Computes checksum
                     ├── Writes: processed/discovery/dim_spots_core/...
                     ├── Writes: processed/discovery/dim_spot_*/...
                     └── Writes: processed/discovery/events/... (`changed`)

S3 Event / manifest trigger
     │
     └──▶ Catalog Builder Lambda
            ├── Reads: append-only discovery Parquet tables
            └── Writes: processed/discovery/catalog_latest/...
```

## Planned Pipeline (Not Yet Implemented)

```
S3 raw layer
     │
     ├──▶ Discovery processors ──▶ processed discovery layer
     │                             - append-only version tables
     │                             - append-only lifecycle events
     │                             - latest catalog snapshot
     │
     ├──▶ Forecast processors ──▶ processed forecast layer
     │                   - canonical per-spot batch outputs
     │                   - timezone-day presentation artifacts
     │                   - historical Parquet partitioned by forecast date
     │
     └──▶ Future API / query layer
                         - current reads from discovery plus forecast canonical/presentation layers
                         - historical reads from forecast history Parquet
```

See [Storage Layout](../data_architecture/storage-layout.md) for the bucket layout, [Forecast Pipeline](../data_architecture/forecast-pipeline.md) for the forecast batch model, [Discovery Schema](../data_architecture/discovery-schema.md) for the discovery Parquet tables, [Forecast Schema](../data_architecture/forecast-schema.md) for the forecast Parquet tables, and [API Design](../api/README.md) for the planned API.

## Error Handling

| Layer | Mechanism |
|-------|-----------|
| HTTP requests | 3 retries with exponential backoff (1s, 2s, 4s) + jitter (0-1s) |
| Rate limiting (429) | Caught by retry logic, logged with headers |
| Lambda failures | SQS visibility timeout (3x function timeout), then retry |
| Persistent failures | Dead-letter queue after 3 failed attempts, 7-day retention |
| Taxonomy rate limiting | 500ms delay between every request (legacy flow only) |
