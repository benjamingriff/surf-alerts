# Spot Scraper

> **Status: IMPLEMENTED** | Last verified: 2026-03-08

Scrapes spot metadata from the Surfline `/reports` endpoint. SQS-triggered Docker Lambda.

**Package:** `packages/scrapers/spot_scraper/`

> **Storage note:** The current Lambda still flattens the response before writing to S3. The raw/processed split below describes the target storage contract after the layered storage rework.

## Endpoint Scraped

```
GET /kbyg/spots/reports?spotId={spot_id}
```

This is the richest spot endpoint — returns name, location, timezone, cameras, travel details, ability levels, and board types.

## How It Works

1. Receives SQS message with `spot_id`, `bucket`, `prefix`
2. Makes 1 HTTP request to Surfline `/reports` endpoint
3. Writes the raw `/reports` response to S3
4. A downstream processor canonicalizes the payload, computes a checksum, and appends new discovery versions when content changes

## Raw Output Format

The scraper should write the unflattened Surfline `/reports` payload into the raw layer:

```text
raw/spot_report/spot_id=<spot_id>/scrape_date=YYYY-MM-DD/run_id=<run_id>.json.gz
```

## Canonical Spot Shape

Downstream processing should first build a canonical spot object shaped like:

```json
{
  "scraped_at": "2026-01-17T14:43:39Z",
  "spot": {
    "spot_id": "584204204e65fad6a77090d2",
    "name": "Rest Bay",
    "lat": 51.4784,
    "lon": -3.8281,
    "timezone": "Europe/London",
    "utc_offset": 0,
    "abbr_timezone": "GMT",
    "href": "/surf-report/rest-bay/...",
    "breadcrumbs": ["Europe", "United Kingdom", "Wales"],
    "subregion": "Glamorgan Heritage Coast",
    "cameras": [
      {
        "id": "...",
        "title": "Rest Bay",
        "stream_url": "https://...",
        "still_url": "https://...",
        "is_premium": false
      }
    ],
    "ability_levels": ["BEGINNER", "INTERMEDIATE", "ADVANCED"],
    "board_types": ["SHORTBOARD", "FUNBOARD", "LONGBOARD"],
    "travel_details": {
      "description": "A consistent beach break...",
      "break_type": ["BEACH_BREAK"],
      "access": "Easy beach access...",
      "hazards": "Rips, rocks on low tide...",
      "best_season": ["AUTUMN", "WINTER"],
      "best_tide": ["MID", "HIGH"],
      "best_swell_direction": ["SW", "W"],
      "best_wind_direction": ["NE", "E"],
      "best_size": "3-6ft",
      "bottom": ["SAND"],
      "crowd_factor": "Moderate",
      "spot_rating": 3
    }
  }
}
```

This canonical object is then normalized into the Parquet discovery model:

- `processed/discovery/dim_spots_core/...`
- `processed/discovery/dim_spot_location/...`
- `processed/discovery/dim_spot_breadcrumbs/...`
- `processed/discovery/dim_spot_cameras/...`
- `processed/discovery/dim_spot_ability_levels/...`
- `processed/discovery/dim_spot_board_types/...`
- `processed/discovery/dim_spot_travel_details/...`

If the canonicalized payload produces the same checksum as the latest known version for that `spot_id`, no new rows should be written.

If the checksum differs, the processor should:

1. Append a `changed` row to `processed/discovery/events/...`
2. Append a new version row to `dim_spots_core`
3. Append new child rows keyed by the new `spot_version_id`
4. Trigger a rebuild of `processed/discovery/catalog_latest/`

## Infrastructure

| Setting | Value |
|---------|-------|
| Timeout | 60s |
| Memory | 1024 MB |
| Max concurrency | 5 |
| SQS batch size | 1 |
| DLQ max receives | 3 |

See [Surfline Spot Endpoints](../surfline/spot-endpoints.md) for the raw API response schema, [Discovery Schema](../data_architecture/discovery-schema.md) for the Parquet model, and [Storage Layout](../data_architecture/storage-layout.md) for the target bucket structure.
