# Spot Scraper

> **Status: IMPLEMENTED** | Last verified: 2026-03-08

Scrapes spot metadata from the Surfline `/reports` endpoint. SQS-triggered Docker Lambda.

**Package:** `packages/scrapers/spot_scraper/`

## Endpoint Scraped

```
GET /kbyg/spots/reports?spotId={spot_id}
```

This is the richest spot endpoint — returns name, location, timezone, cameras, travel details, ability levels, and board types.

## How It Works

1. Receives SQS message with `spot_id`, `bucket`, `prefix`
2. Makes 1 HTTP request to Surfline `/reports` endpoint
3. Parses and restructures the response (flattens nested objects)
4. Writes gzip-compressed JSON to S3

## Output Format

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

## Infrastructure

| Setting | Value |
|---------|-------|
| Timeout | 60s |
| Memory | 1024 MB |
| Max concurrency | 5 |
| SQS batch size | 1 |
| DLQ max receives | 3 |

See [Surfline Spot Endpoints](../surfline/spot-endpoints.md) for the raw API response schema.
