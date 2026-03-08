# Data Flow

> **Status: IMPLEMENTED** (scrape + store) | **PLANNED** (Parquet + API)

## Current Pipeline (Implemented)

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
│  S3 Bucket     │     Gzip-compressed JSON
│  {stack}-data  │     Path: {prefix}.gz
└────────────────┘
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
3. Responses combined into single JSON with `metadata.json` + `data.json`
4. Gzip-compressed and written to S3

**Units requested:** `swellHeight=FT`, `waveHeight=FT`, `windSpeed=MPH`, `temperature=C`, `tideHeight=M`

> **Note:** Tides are currently scraped in meters. Planned change: switch to `tideHeight=FT` to match the [Forecast Schema](../data_architecture/forecast-schema.md) which specifies feet.

### Spot Scraper Flow

1. SQS message arrives with `spot_id`, `bucket`, `prefix`
2. Lambda makes 1 HTTP request to `/kbyg/spots/reports?spotId={spot_id}`
3. Response parsed and restructured (flattens travel details, cameras, breadcrumbs)
4. Gzip-compressed and written to S3

### Scheduled Scraper Flow (Currently Disabled)

```
EventBridge Cron
     │
     ├── 06:00 UTC ──▶ Sitemap Scraper ──▶ spots/{date}/sitemap.json.gz
     │
     ├── 06:00 UTC ──▶ Taxonomy Scraper ──▶ taxonomy/{date}/taxonomy.json.gz
     │                  (recursive, 500ms delay between requests)
     │
     └── 06:15 UTC ──▶ Spot Reconciler
                        ├── Reads: sitemap + taxonomy + previous state
                        ├── Merges and detects changes (SHA256 checksums)
                        └── Writes: spots_data.json.gz, changes.json.gz, state.json.gz
```

## Planned Pipeline (Not Yet Implemented)

```
S3 (Raw JSON)
     │
     ├──▶ ETL Job ──▶ Parquet (historical archive)
     │                 Partitioned: year/month/spot_id
     │                 7 fact/dim tables
     │
     └──▶ ETL Job ──▶ PostgreSQL (current forecast)
                       Latest scrape only
                       Materialized view
                       │
                       ▼
                  FastAPI + Lambda
                  (REST API)
```

See [Forecast Schema](../data_architecture/forecast-schema.md) for the Parquet table definitions and [API Design](../api/README.md) for the planned API.

## Error Handling

| Layer | Mechanism |
|-------|-----------|
| HTTP requests | 3 retries with exponential backoff (1s, 2s, 4s) + jitter (0-1s) |
| Rate limiting (429) | Caught by retry logic, logged with headers |
| Lambda failures | SQS visibility timeout (3x function timeout), then retry |
| Persistent failures | Dead-letter queue after 3 failed attempts, 7-day retention |
| Taxonomy rate limiting | 500ms delay between every request |
