# Surfline API

> **Status: IMPLEMENTED** | Last verified: 2026-03-06

Comprehensive reference for the Surfline API endpoints discovered through live testing. All endpoints were verified on 2026-03-06 using Rest Bay (`584204204e65fad6a77090d2`) as the test spot and Severn Estuary (`612801eb3f4e20988f77c71f`) as the test subregion.

## Base URLs

| Service | URL |
|---------|-----|
| API | `https://services.surfline.com` |
| Sitemap | `https://www.surfline.com/sitemaps/spots.xml` |
| Search | `https://services.surfline.com/search/site` |

## Required Headers

All `/kbyg/*` and `/taxonomy` endpoints require browser-like headers to avoid bot detection:

```
Accept: application/json
Accept-Language: en-US,en;q=0.9
Referer: https://www.surfline.com/
Origin: https://www.surfline.com
```

Our scrapers use `curl-cffi` with Chrome impersonation to bypass Cloudflare bot protection. Standard `requests` or `urllib` will be blocked.

## Common Response Structure

Most `/kbyg/*` endpoints return responses wrapped in this structure:

```json
{
  "associated": {
    "units": { ... },
    "utcOffset": -8,
    "timezone": "America/Los_Angeles",
    "abbrTimezone": "PST",
    "location": { "lon": -3.83, "lat": 51.48 },
    "forecastLocation": { ... },
    "offshoreLocation": { ... },
    "runInitializationTimestamp": 1709683200
  },
  "data": { ... },
  "permissions": {
    "violations": [],
    "data": { ... }
  }
}
```

- **`associated`** — metadata about the spot, units, timezone, and model run info
- **`data`** — the actual forecast/spot data
- **`permissions`** — auth status; `violations` array is empty for free data, populated for premium-locked content

## Units Configuration

Forecast endpoints accept `units[*]` query parameters to control response units:

| Parameter | Values | Default |
|-----------|--------|---------|
| `units[waveHeight]` | `FT`, `M` | `FT` |
| `units[swellHeight]` | `FT`, `M` | `FT` |
| `units[windSpeed]` | `MPH`, `KPH`, `KTS` | `KPH` |
| `units[temperature]` | `C`, `F` | `F` |
| `units[tideHeight]` | `M`, `FT` | `FT` |

**Our scraper requests:** `units[temperature]=C`, `units[tideHeight]=FT` — we always store temperature in Celsius and tide heights in feet.

## Authentication

All documented endpoints work **without authentication** for basic data. No API key is needed for free-tier data.

## Rate Limiting and Bot Evasion

### Cloudflare Protection

Surfline uses Cloudflare for bot detection. Requests made with standard HTTP clients (`requests`, `urllib`, `httpx`) are blocked with 403 responses. Our scrapers use `curl-cffi` with Chrome browser impersonation to bypass this.

### Rate Limiting (429s)

We've observed 429 responses when making requests too quickly. Our HTTP client handles this with:
- **3 retries** with exponential backoff
- **Jitter** (0-1s random delay) added to backoff
- **Initial backoff:** 1 second, doubling each retry

The taxonomy scraper adds a **500ms delay** between every request as a preventive measure when making hundreds of sequential calls.

### Recommendations

- Keep concurrency low per IP (our Lambda max concurrency is 2-5)
- Add delays between sequential requests to the same endpoint
- Use `cacheEnabled=true` where supported to reduce server load
- Rotate request patterns / avoid predictable timing

## Quick Reference

| Category | Endpoint | We Scrape? | Doc |
|----------|----------|------------|-----|
| Spot Data | `/kbyg/spots/reports` | Yes (spot_scraper) | [Spot Endpoints](spot-endpoints.md) |
| Spot Data | `/kbyg/spots/details` | No | [Spot Endpoints](spot-endpoints.md) |
| Spot Data | `/kbyg/spots/nearby` | No | [Spot Endpoints](spot-endpoints.md) |
| Forecast | `/kbyg/spots/forecasts/rating` | Yes (forecast_scraper) | [Forecast Endpoints](forecast-endpoints.md) |
| Forecast | `/kbyg/spots/forecasts/wave` | Yes (forecast_scraper) | [Forecast Endpoints](forecast-endpoints.md) |
| Forecast | `/kbyg/spots/forecasts/wind` | Yes (forecast_scraper) | [Forecast Endpoints](forecast-endpoints.md) |
| Forecast | `/kbyg/spots/forecasts/tides` | Yes (forecast_scraper) | [Forecast Endpoints](forecast-endpoints.md) |
| Forecast | `/kbyg/spots/forecasts/weather` | Yes (forecast_scraper) | [Forecast Endpoints](forecast-endpoints.md) |
| Forecast | `/kbyg/spots/forecasts/sunlight` | Yes (forecast_scraper) | [Forecast Endpoints](forecast-endpoints.md) |
| Forecast | `/kbyg/spots/forecasts/surf` | No | [Forecast Endpoints](forecast-endpoints.md) |
| Forecast | `/kbyg/spots/forecasts/conditions` | No | [Forecast Endpoints](forecast-endpoints.md) |
| Region | `/kbyg/regions/overview` | No | [Spot Endpoints](spot-endpoints.md) |
| Map | `/kbyg/mapview` | No | [Spot Endpoints](spot-endpoints.md) |
| Search | `/search/site` | No | [Taxonomy & Search](taxonomy-and-search.md) |
| Taxonomy | `/taxonomy` (type=taxonomy) | Yes (taxonomy_scraper) | [Taxonomy & Search](taxonomy-and-search.md) |
| Taxonomy | `/taxonomy` (type=spot) | No | [Taxonomy & Search](taxonomy-and-search.md) |
| Sitemap | `/sitemaps/spots.xml` | Yes (sitemap_scraper) | [Taxonomy & Search](taxonomy-and-search.md) |

## Endpoints Not Found (404)

These endpoints were tested on 2026-03-06 and returned 404 — documented here to avoid re-testing:

| Endpoint | Notes |
|----------|-------|
| `/kbyg/spots/consistency` | Possibly removed or never existed |
| `/kbyg/regions/listings` | Not a valid endpoint |
| `/kbyg/spots/forecasts/barrels` | No barrel-specific forecast endpoint |
| `/kbyg/spots/forecasts/current` | Use `/reports` for current conditions |
| `/kbyg/buoy` | Buoy data not exposed via this API |
| `/kbyg/spots/travel` | Travel info is nested in `/reports` response |
| `/taxonomy/search` | Use `/search/site` instead |
| `/taxonomy/details/{id}` | Use `/taxonomy?type=spot&id={id}` instead |
| `/kbyg/spots/nearme` | Lat/lon based — use `/mapview` with bounding box instead |
