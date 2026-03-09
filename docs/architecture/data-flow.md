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
┌────────────────┐     EventBridge / manifest-driven trigger
│  Processor     │──── Transform raw payloads into canonical data
│  (planned)     │
└───────┬────────┘
        │
        ├──▶ processed/...      Canonical operational snapshots
        └──▶ control/...        Manifests, checkpoints, completion records
```

### Forecast Scraper Flow

1. SQS message arrives with `spot_id`, `bucket`, `prefix`
2. Lambda makes 6 sequential HTTP requests to Surfline:
   - `/kbyg/spots/forecasts/rating` (5 days, hourly)
   - `/kbyg/spots/forecasts/sunlight` (16 days, daily)
   - `/kbyg/spots/forecasts/tides` (6 days, irregular)
   - `/kbyg/spots/forecasts/wave` (5 days, hourly)
   - `/kbyg/spots/forecasts/weather` (16 days, hourly)
   - `/kbyg/spots/forecasts/wind` (5 days, hourly)
3. Responses combined into one raw forecast envelope
4. Gzip-compressed and written to `raw/forecast/...`

**Planned downstream outputs:**
- `processed/forecast/canonical/...` - immutable per-scrape normalized object
- `processed/forecast/latest/...` - mutable latest snapshot per spot
- `processed/forecast/analytics/...` - analytical Parquet tables

**Units requested:** `swellHeight=FT`, `waveHeight=FT`, `windSpeed=MPH`, `temperature=C`, `tideHeight=M`

> **Note:** Tides are currently scraped in meters. Planned change: switch to `tideHeight=FT` to match the [Forecast Schema](../data_architecture/forecast-schema.md) which specifies feet.

### Spot Scraper Flow

1. SQS message arrives with `spot_id`, `bucket`, `prefix`
2. Lambda makes 1 HTTP request to `/kbyg/spots/reports?spotId={spot_id}`
3. Response written to `raw/spot_report/...`
4. A downstream processor flattens it into canonical discovery data

**Planned downstream outputs:**
- `processed/discovery/spots/spot_id=<id>/latest.json.gz` - canonical spot record
- `processed/discovery/latest/catalog.json.gz` - latest full catalog

### Scheduled Scraper Flow (Currently Disabled)

```
EventBridge Cron
     │
     ├── 06:00 UTC ──▶ Sitemap Scraper ──▶ raw/sitemap/...
     │
     ├── 06:00 UTC ──▶ Taxonomy Scraper ──▶ raw/taxonomy/...
     │                  (recursive, 500ms delay between requests)
     │
     └── 06:15 UTC ──▶ Spot Reconciler / Discovery Processor
                        ├── Reads: raw sitemap + raw taxonomy + previous latest state
                        ├── Merges and detects changes (SHA256 checksums)
                        └── Writes: processed/discovery/snapshots/, changes/, latest/
```

## Planned Pipeline (Not Yet Implemented)

```
S3 raw layer
     │
     ├──▶ Processor ──▶ processed canonical layer
     │                   - discovery snapshots and changes
     │                   - per-spot latest forecast
     │
     ├──▶ Processor ──▶ processed analytics layer
     │                   - forecast Parquet archive
     │                   - partitioned by year/month/spot_id
     │
     └──▶ Future API / query layer
                         - current reads from processed latest snapshots
                         - historical reads from Parquet
```

See [Storage Layout](../data_architecture/storage-layout.md) for the bucket layout, [Forecast Schema](../data_architecture/forecast-schema.md) for the Parquet table definitions, and [API Design](../api/README.md) for the planned API.

## Error Handling

| Layer | Mechanism |
|-------|-----------|
| HTTP requests | 3 retries with exponential backoff (1s, 2s, 4s) + jitter (0-1s) |
| Rate limiting (429) | Caught by retry logic, logged with headers |
| Lambda failures | SQS visibility timeout (3x function timeout), then retry |
| Persistent failures | Dead-letter queue after 3 failed attempts, 7-day retention |
| Taxonomy rate limiting | 500ms delay between every request |
