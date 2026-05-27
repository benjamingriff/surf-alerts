# Forecast Scraper

> **Status: IMPLEMENTED** | Last verified: 2026-05-27

Scrapes the Surfline forecast endpoints relevant to surf conditions for one planned spot in a Forecast Run. It is an SQS-triggered Docker Lambda and writes raw S3 objects only for successful all-or-nothing scrapes.

**Package:** `packages/scrapers/forecast_scraper/`

## Endpoints Scraped

| Endpoint | Days | Interval | Units Requested |
|----------|------|----------|-----------------|
| `/kbyg/spots/forecasts/rating` | 5 | Hourly | — |
| `/kbyg/spots/forecasts/tides` | 6 | Irregular | `tideHeight=FT` |
| `/kbyg/spots/forecasts/wave` | 5 | Hourly | `swellHeight=FT`, `waveHeight=FT` |
| `/kbyg/spots/forecasts/wind` | 5 | Hourly | `windSpeed=MPH` |

Weather and sunlight endpoints are intentionally not collected in v1 because they are not surf-condition inputs for this project. There are no v1 weather or sunlight forecast tables.

## How It Works

1. Receives one SQS message from the Forecast Run Planner for a planned spot.
2. Makes sequential HTTP requests to rating, tides, wave, and wind using curl-cffi Chrome impersonation.
3. Treats the scrape as all-or-nothing across the four endpoints.
4. Builds one raw forecast envelope with forecast run lineage and spot metadata.
5. Writes gzip-compressed JSON to S3 only for successful scrapes.
6. Emits a terminal completion message to the forecast completion queue for both caught scrape success and caught scrape failure.

Failed scrapes do not write raw S3 objects. Completion-send or other infrastructure/control failures still raise so SQS/DLQ behavior can catch system failures.

## Forecast Run Context

Forecast scrapes are orchestrated by the Forecast Run Planner, not by S3 manifests.

The planner runs hourly from EventBridge, computes the due stored UTC offset for the configured local scrape time, queries live processed spots for only that offset, creates DynamoDB forecast run/planned-spot control state, and enqueues one scrape message per spot.

Each scrape message carries forecast run metadata, spot metadata, scheduled UTC time, UTC offset, timezone, and the raw bucket/key destination.

## Raw Output Format

Successful scrapes produce one immutable raw envelope. The envelope includes only two timestamp metadata fields: `scheduled_utc_time` and `scraped_at`.

```json
{
  "schema_version": 1,
  "source_type": "surfline_forecast",
  "forecast_run_id": "forecast#offset=1#scrape_date=2026-05-26#time=04-00",
  "spot_id": "584204204e65fad6a77090d2",
  "spot_version_id": "spot-version-id",
  "spot_name": "Rest Bay",
  "scheduled_utc_time": "2026-05-26T03:00:00Z",
  "scraped_at": "2026-05-26T03:04:00Z",
  "utc_offset": 1,
  "timezone": "Europe/London",
  "lat": 51.49,
  "lon": -3.72,
  "raw_payload": {
    "rating": {},
    "tides": {},
    "wave": {},
    "wind": {}
  }
}
```

Raw keys are partitioned by UTC scrape date, UTC offset, forecast run ID, and spot ID. v1 does not include a per-invocation scrape ID in the raw key.

## Downstream Processing

The Forecast Spot Processor consumes completion messages. For failed scrape completions it records terminal scrape state in DynamoDB and skips S3/Postgres work. For successful completions it reads the raw object, transforms rating, wave, swells, wind, and tides, and inserts rows into Supabase/Postgres fact tables in one transaction:

- `forecast_fact_rating`
- `forecast_fact_wave`
- `forecast_fact_swells`
- `forecast_fact_wind`
- `forecast_fact_tides`

Postgres inserts are append-only and use `ON CONFLICT DO NOTHING` against table unique constraints.

## Row Counts Per Successful Scrape

| Forecast Type | Rows | Cadence |
|---------------|------|---------|
| Rating | ~120 | Hourly, 5 days |
| Tides | ~168 | Irregular, including NORMAL/HIGH/LOW entries |
| Wave | ~120 | Hourly, 5 days |
| Swells | ~720 | Six swell slots for each wave timestamp, including zero-height swells |
| Wind | ~120 | Hourly, 5 days |

## Infrastructure

| Setting | Value |
|---------|-------|
| Timeout | 60s |
| Memory | 1024 MB |
| Max concurrency | 2 |
| SQS batch size | 1 |
| DLQ max receives | 3 |

See [Forecast Pipeline](../data_architecture/forecast-pipeline.md), [Forecast Schema](../data_architecture/forecast-schema.md), and [Surfline Forecast Endpoints](../surfline/forecast-endpoints.md).
