# Forecast Scraper

> **Status: IMPLEMENTED** | Last verified: 2026-03-08

Scrapes the Surfline forecast endpoints relevant to surf conditions for a single spot per invocation. SQS-triggered Docker Lambda.

**Package:** `packages/scrapers/forecast_scraper/`

> **Storage note:** The current Lambda already combines the 6 endpoint responses before writing to S3. The raw/processed paths below describe the target storage contract after the layered storage rework.

## Endpoints Scraped

| Endpoint | Days | Interval | Units Requested |
|----------|------|----------|-----------------|
| `/kbyg/spots/forecasts/rating` | 5 | Hourly | — |
| `/kbyg/spots/forecasts/tides` | 6 | Irregular | `tideHeight=M` |
| `/kbyg/spots/forecasts/wave` | 5 | Hourly | `swellHeight=FT`, `waveHeight=FT` |
| `/kbyg/spots/forecasts/wind` | 5 | Hourly | `windSpeed=MPH` |

Weather and sunlight endpoints are intentionally not collected in v1 because they are not surf-condition inputs for this project.

> **Note:** Tides are currently scraped in meters. Planned change to feet — see [Forecast Schema](../data_architecture/forecast-schema.md) for details.

## How It Works

1. Receives SQS message with `spot_id`, `bucket`, `prefix`, and forecast run metadata
2. Makes sequential HTTP requests to the selected Surfline forecast endpoints (curl-cffi, Chrome impersonation)
3. Parses JSON responses
4. Combines the selected responses into a single raw forecast envelope
5. Writes gzip-compressed JSON to S3 at `raw/forecast/...`
6. Emits a completion marker for the batch member scrape

The scraper is only the raw-layer writer. Batch completeness, canonicalization, presentation publishing, and history writes are handled downstream.

## Run Context

Forecast scrapes are orchestrated as offset-local forecast runs rather than standalone spot refreshes.

The scheduler should:

1. run every hour in UTC
2. determine which local timezone scrape times are due
3. build one run manifest per due timezone-local day
4. enqueue one message per `spot_id` in that batch

Each SQS message should carry:

- `spot_id`
- `forecast_run_id`
- `timezone`
- `local_batch_date`
- `scheduled_local_time`
- `bucket`
- `prefix`

## Raw Output Format

The forecast scraper should be treated as a **raw layer writer**. Each scrape lands as one immutable raw object keyed by `run_id`.

Two logical sections per scrape:

**metadata:**
```json
{
  "spot_id": "584204204e65fad6a77090d2",
  "forecast_run_id": "lon-2026-01-17-0700",
  "timezone": "Europe/London",
  "local_batch_date": "2026-01-17",
  "timestamp": "2026-01-17T14:43:39.398066",
  "scraper": "forecast"
}
```

**data:** Contains surf-relevant top-level keys (`rating`, `tides`, `wave`, `wind`), each with `associated`, `data`, and `permissions` objects from the Surfline API response.

Recommended raw key shape:

```text
raw/forecast/utc_offset=<offset>/local_date=YYYY-MM-DD/forecast_run_id=<forecast_run_id>/spot_id=<spot_id>/scrape_run_id=<scrape_run_id>.json.gz
```

## Downstream Processed Outputs

The raw forecast object participates in a manifest-driven run flow:

- `control/completions/...` - per-spot completion marker for the batch
- `processed/forecast/canonical/...` - immutable canonical forecast per spot within a completed forecast run
- `processed/forecast/presentation/...` - one daily timezone-day notification-ready artifact
- `processed/forecast/history/...` - append-only Parquet fact/dimension tables for long-term queries and warehouse loading

The target flow should not depend on a mutable per-spot `latest/` forecast object. Consumers should read either canonical per-run outputs or the timezone-day presentation layer, depending on the use case.

## Row Counts Per Scrape

| Forecast Type | Rows | Cadence |
|---------------|------|---------|
| Rating | 120 | Hourly, 5 days |
| Tides | ~168 | Irregular (HIGH/LOW events + interpolated) |
| Wave | 120 | Hourly, 5 days |
| Wind | 120 | Hourly, 5 days |

## Infrastructure

| Setting | Value |
|---------|-------|
| Timeout | 60s |
| Memory | 1024 MB |
| Max concurrency | 2 |
| SQS batch size | 1 |
| DLQ max receives | 3 |

See [Surfline Forecast Endpoints](../surfline/forecast-endpoints.md) for full API response schemas, [Forecast Pipeline](../data_architecture/forecast-pipeline.md) for the batch/control model, and [Storage Layout](../data_architecture/storage-layout.md) for the target bucket structure.
