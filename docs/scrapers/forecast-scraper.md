# Forecast Scraper

> **Status: IMPLEMENTED** | Last verified: 2026-03-08

Scrapes 6 Surfline forecast endpoints for a single spot per invocation. SQS-triggered Docker Lambda.

**Package:** `packages/scrapers/forecast_scraper/`

## Endpoints Scraped

| Endpoint | Days | Interval | Units Requested |
|----------|------|----------|-----------------|
| `/kbyg/spots/forecasts/rating` | 5 | Hourly | — |
| `/kbyg/spots/forecasts/sunlight` | 16 | Daily | — |
| `/kbyg/spots/forecasts/tides` | 6 | Irregular | `tideHeight=M` |
| `/kbyg/spots/forecasts/wave` | 5 | Hourly | `swellHeight=FT`, `waveHeight=FT` |
| `/kbyg/spots/forecasts/weather` | 16 | Hourly | `temperature=C` |
| `/kbyg/spots/forecasts/wind` | 5 | Hourly | `windSpeed=MPH` |

> **Note:** Tides are currently scraped in meters. Planned change to feet — see [Forecast Schema](../data/forecast-schema.md).

## How It Works

1. Receives SQS message with `spot_id`, `bucket`, `prefix`
2. Makes 6 sequential HTTP requests to Surfline (curl-cffi, Chrome impersonation)
3. Parses JSON responses
4. Combines all 6 responses into a single data structure
5. Writes gzip-compressed JSON to S3 at `{prefix}.gz`

## Output Format

Two logical sections per scrape:

**metadata:**
```json
{
  "spot_id": "584204204e65fad6a77090d2",
  "timestamp": "2026-01-17T14:43:39.398066",
  "scraper": "forecast"
}
```

**data:** Contains 6 top-level keys (`rating`, `sunlight`, `tides`, `wave`, `weather`, `wind`), each with `associated`, `data`, and `permissions` objects from the Surfline API response.

## Row Counts Per Scrape

| Forecast Type | Rows | Cadence |
|---------------|------|---------|
| Rating | 120 | Hourly, 5 days |
| Sunlight | 16 | Daily, 16 days |
| Tides | ~168 | Irregular (HIGH/LOW events + interpolated) |
| Wave | 120 | Hourly, 5 days |
| Weather | 384 | Hourly, 16 days |
| Wind | 120 | Hourly, 5 days |

## Infrastructure

| Setting | Value |
|---------|-------|
| Timeout | 60s |
| Memory | 1024 MB |
| Max concurrency | 2 |
| SQS batch size | 1 |
| DLQ max receives | 3 |

See [Surfline Forecast Endpoints](../surfline/forecast-endpoints.md) for full API response schemas.
