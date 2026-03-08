# Surfline API Reference

Comprehensive reference for the Surfline API endpoints discovered through live testing. All endpoints were verified on 2026-03-06 using Rest Bay (`584204204e65fad6a77090d2`) as the test spot and Severn Estuary (`612801eb3f4e20988f77c71f`) as the test subregion.

## Overview

**Base URL:** `https://services.surfline.com`

**Sitemap URL:** `https://www.surfline.com/sitemaps/spots.xml`

**Search URL:** `https://services.surfline.com/search/site`

### Required Headers

All `/kbyg/*` and `/taxonomy` endpoints require browser-like headers to avoid bot detection:

```
Accept: application/json
Accept-Language: en-US,en;q=0.9
Referer: https://www.surfline.com/
Origin: https://www.surfline.com
```

Our scrapers use `curl-cffi` with Chrome impersonation to bypass Cloudflare bot protection. Standard `requests` or `urllib` will be blocked.

### Common Response Structure

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

- **`associated`** - metadata about the spot, units, timezone, and model run info
- **`data`** - the actual forecast/spot data
- **`permissions`** - auth status; `violations` array is empty for free data, populated for premium-locked content

### Units Configuration

Forecast endpoints accept `units[*]` query parameters to control response units:

| Parameter | Values | Default |
|-----------|--------|---------|
| `units[waveHeight]` | `FT`, `M` | `FT` |
| `units[swellHeight]` | `FT`, `M` | `FT` |
| `units[windSpeed]` | `MPH`, `KPH`, `KTS` | `KPH` |
| `units[temperature]` | `C`, `F` | `F` |
| `units[tideHeight]` | `M`, `FT` | `FT` |

### Authentication

All documented endpoints work **without authentication** for basic data. Premium data (extended forecasts, cam rewinds, etc.) returns `permissions.violations` indicating what's locked. No API key is needed for free-tier data.

---

## Spot Data

### GET /kbyg/spots/reports

Full spot report with metadata, location, conditions, cameras, and travel details.

```
GET /kbyg/spots/reports?spotId={spotId}
```

**Parameters:**
| Param | Required | Description |
|-------|----------|-------------|
| `spotId` | Yes | Surfline spot ID (24-char hex) |

**Response top-level keys:** `spot`, `associated`, `forecast`, `report`

```json
{
  "spot": {
    "name": "Rest Bay",
    "lat": 51.4784,
    "lon": -3.8281,
    "breadcrumb": [
      { "name": "Europe", "href": "..." },
      { "name": "United Kingdom", "href": "..." },
      { "name": "Wales", "href": "..." }
    ],
    "subregion": { "_id": "...", "name": "Glamorgan Heritage Coast" },
    "cameras": [
      {
        "_id": "...",
        "title": "Rest Bay",
        "streamUrl": "https://...",
        "stillUrl": "https://...",
        "isPremium": false
      }
    ],
    "abilityLevels": ["BEGINNER", "INTERMEDIATE", "ADVANCED"],
    "boardTypes": ["SHORTBOARD", "FUNBOARD", "LONGBOARD"],
    "travelDetails": {
      "description": "A consistent beach break...",
      "breakType": ["BEACH_BREAK"],
      "access": "Easy beach access...",
      "hazards": "Rips, rocks on low tide...",
      "best": {
        "season": { "value": ["AUTUMN", "WINTER"] },
        "tide": { "value": ["MID", "HIGH"] },
        "swellDirection": { "value": ["SW", "W"] },
        "windDirection": { "value": ["NE", "E"] },
        "size": { "description": "3-6ft" }
      },
      "bottom": { "value": ["SAND"] },
      "crowdFactor": { "summary": "Moderate" },
      "spotRating": { "rating": 3 }
    }
  },
  "associated": {
    "timezone": "Europe/London",
    "utcOffset": 0,
    "abbrTimezone": "GMT"
  }
}
```

**Notes:** This is the richest spot endpoint. Our `spot_scraper` uses this as its primary data source. No `timezonefinder` needed - timezone comes directly from the API.

---

### GET /kbyg/spots/details

Minimal spot info - primarily name and associated metadata.

```
GET /kbyg/spots/details?spotId={spotId}
```

**Parameters:**
| Param | Required | Description |
|-------|----------|-------------|
| `spotId` | Yes | Surfline spot ID |

**Response:** Returns `associated` metadata and basic spot identification. Less data than `/reports` - mainly useful if you only need the spot name or timezone.

---

### GET /kbyg/spots/nearby

Returns nearby spots with current conditions and ratings.

```
GET /kbyg/spots/nearby?spotId={spotId}
```

**Parameters:**
| Param | Required | Description |
|-------|----------|-------------|
| `spotId` | Yes | Surfline spot ID |

**Response:** Array of nearby spots with:
- Spot ID, name, and location
- Current surf conditions and ratings
- Current wave heights (min/max)
- Distance from the queried spot

---

## Forecasts

All forecast endpoints share common parameters:

| Param | Required | Description |
|-------|----------|-------------|
| `spotId` | Yes | Surfline spot ID |
| `days` | No | Number of forecast days (default varies by endpoint) |
| `intervalHours` | No | Data interval in hours (1, 3, 6, etc.) |
| `cacheEnabled` | No | Enable server-side caching (`true`/`false`) |

### GET /kbyg/spots/forecasts/rating

Surf quality ratings over time on a 0-6 scale.

```
GET /kbyg/spots/forecasts/rating?spotId={spotId}&days=5&intervalHours=1&cacheEnabled=true
```

**Response `data` structure:**

```json
{
  "rating": [
    {
      "timestamp": 1709683200,
      "utcOffset": 0,
      "rating": {
        "key": "FAIR_TO_GOOD",
        "value": 3.5
      }
    }
  ]
}
```

**Rating scale:** 0 (FLAT) to 6 (EPIC). Keys: `FLAT`, `VERY_POOR`, `POOR`, `POOR_TO_FAIR`, `FAIR`, `FAIR_TO_GOOD`, `GOOD`, `EPIC`.

**Premium:** Free for ~5 days. Extended forecasts (16+ days) require premium.

---

### GET /kbyg/spots/forecasts/wave

Wave height, period, direction, and individual swell breakdown.

```
GET /kbyg/spots/forecasts/wave?spotId={spotId}&days=5&intervalHours=1&cacheEnabled=true&units[swellHeight]=FT&units[waveHeight]=FT
```

**Response `data` structure:**

```json
{
  "wave": [
    {
      "timestamp": 1709683200,
      "surf": {
        "min": 2.1,
        "max": 3.4,
        "plus": false,
        "humanRelation": "Waist to chest",
        "raw": { "min": 2.08, "max": 3.42 },
        "optimalScore": 2
      },
      "swells": [
        {
          "height": 4.2,
          "period": 12,
          "direction": 245.6,
          "directionMin": 240.1,
          "optimalScore": 2
        }
      ],
      "power": 148.5
    }
  ]
}
```

**Key fields:**
- `surf.min`/`surf.max` - combined surf height range
- `surf.humanRelation` - human-readable size ("Knee to waist", "Overhead", etc.)
- `swells[]` - individual swell components with height, period, and direction
- `power` - wave energy metric

---

### GET /kbyg/spots/forecasts/wind

Wind speed, direction, and gusts.

```
GET /kbyg/spots/forecasts/wind?spotId={spotId}&days=5&intervalHours=1&corrected=false&cacheEnabled=true&units[windSpeed]=MPH
```

**Response `data` structure:**

```json
{
  "wind": [
    {
      "timestamp": 1709683200,
      "speed": 12.5,
      "direction": 225,
      "directionType": "Onshore",
      "gust": 18.3,
      "optimalScore": 0
    }
  ]
}
```

**Key fields:**
- `speed` - sustained wind speed
- `gust` - gust speed
- `direction` - wind direction in degrees
- `directionType` - relation to break: `Offshore`, `Cross-shore`, `Onshore`, `Cross-offshore`, `Cross-onshore`
- `optimalScore` - 0 (bad) to 2 (optimal)

---

### GET /kbyg/spots/forecasts/tides

Tide heights and high/low markers.

```
GET /kbyg/spots/forecasts/tides?spotId={spotId}&days=6&cacheEnabled=true&units[tideHeight]=M
```

**Response `data` structure:**

```json
{
  "tides": [
    {
      "timestamp": 1709683200,
      "utcOffset": 0,
      "type": "HIGH",
      "height": 8.92
    },
    {
      "timestamp": 1709704800,
      "type": "LOW",
      "height": 1.23
    },
    {
      "timestamp": 1709712000,
      "type": "NORMAL",
      "height": 4.56
    }
  ]
}
```

**Types:** `HIGH`, `LOW`, `NORMAL` (interpolated data points between highs and lows).

**Note:** No `intervalHours` parameter - tide data comes at natural high/low points plus interpolated values.

---

### GET /kbyg/spots/forecasts/weather

Temperature and weather conditions.

```
GET /kbyg/spots/forecasts/weather?spotId={spotId}&days=16&intervalHours=1&cacheEnabled=true&units[temperature]=C
```

**Response `data` structure:**

```json
{
  "weather": [
    {
      "timestamp": 1709683200,
      "temperature": 8.5,
      "condition": "PARTLY_CLOUDY",
      "pressure": 1013
    }
  ]
}
```

---

### GET /kbyg/spots/forecasts/sunlight

Sunrise and sunset times, plus dawn/dusk.

```
GET /kbyg/spots/forecasts/sunlight?spotId={spotId}&days=16&intervalHours=1
```

**Response `data` structure:**

```json
{
  "sunlight": [
    {
      "midnight": 1709683200,
      "sunrise": 1709707080,
      "sunset": 1709745360,
      "dawn": 1709705280,
      "dusk": 1709747160
    }
  ]
}
```

**Note:** One entry per day regardless of `intervalHours`. Each entry gives timestamps for midnight, dawn, sunrise, sunset, and dusk.

---

### GET /kbyg/spots/forecasts/surf

Surf height forecast with human-readable descriptions.

```
GET /kbyg/spots/forecasts/surf?spotId={spotId}&days=5&intervalHours=1
```

**Response `data` structure:**

```json
{
  "surf": [
    {
      "timestamp": 1709683200,
      "surf": {
        "min": 2.1,
        "max": 3.4,
        "plus": false,
        "humanRelation": "Waist to chest",
        "raw": { "min": 2.08, "max": 3.42 },
        "optimalScore": 2
      }
    }
  ]
}
```

**Note:** Similar to the `surf` object within the wave endpoint, but without swell breakdown. Use the `/wave` endpoint if you need individual swell components.

---

### GET /kbyg/spots/forecasts/conditions

Daily conditions summary with forecaster analysis.

```
GET /kbyg/spots/forecasts/conditions?spotId={spotId}&days=5
```

**Response `data` structure:**

```json
{
  "conditions": [
    {
      "timestamp": 1709683200,
      "forecaster": {
        "name": "John Smith",
        "avatar": "https://..."
      },
      "observation": "Clean lines with light offshore winds...",
      "am": {
        "maxHeight": 4,
        "minHeight": 2,
        "humanRelation": "Waist to chest",
        "rating": "FAIR_TO_GOOD"
      },
      "pm": {
        "maxHeight": 3,
        "minHeight": 1.5,
        "humanRelation": "Knee to waist",
        "rating": "FAIR"
      },
      "dayToWatch": false
    }
  ]
}
```

**Key fields:**
- `observation` - human-written forecast text from Surfline forecaster
- `am`/`pm` - separate morning and afternoon forecasts
- `dayToWatch` - boolean flag for standout days

**Note:** No `intervalHours` parameter - returns one entry per day with AM/PM split.

---

## Regions

### GET /kbyg/regions/overview

Region overview with spots list and current conditions.

```
GET /kbyg/regions/overview?subregionId={subregionId}
```

**Parameters:**
| Param | Required | Description |
|-------|----------|-------------|
| `subregionId` | Yes | Surfline subregion ID |

**Response:** Contains:
- List of spots in the region with current conditions and ratings
- Regional forecast summary
- Highlighted spots / standout conditions

---

## Map / Discovery

### GET /kbyg/mapview

Returns all surf spots within a geographic bounding box. Useful for building map-based UIs or discovering spots in an area.

```
GET /kbyg/mapview?north={lat}&south={lat}&east={lon}&west={lon}
```

**Parameters:**
| Param | Required | Description |
|-------|----------|-------------|
| `north` | Yes | Northern latitude boundary |
| `south` | Yes | Southern latitude boundary |
| `east` | Yes | Eastern longitude boundary |
| `west` | Yes | Western longitude boundary |

**Response:** Array of spots within the bounding box, each with:
- Spot ID, name, coordinates
- Current conditions and ratings
- Current surf heights

**Example:** To get all spots in South Wales:
```
GET /kbyg/mapview?north=51.8&south=51.3&east=-3.0&west=-5.5
```

---

## Search

### GET /search/site

Elasticsearch-powered search across spots, subregions, and geonames.

```
GET /search/site?q={query}&querySize={limit}
```

**Parameters:**
| Param | Required | Description |
|-------|----------|-------------|
| `q` | Yes | Search query string |
| `querySize` | No | Max results to return (default: 10) |

**Response:**

```json
[
  {
    "hits": {
      "hits": [
        {
          "_source": {
            "name": "Rest Bay",
            "href": "/surf-report/rest-bay/584204204e65fad6a77090d2",
            "location": { "coordinates": [-3.83, 51.48] },
            "breadCrumbs": ["Europe", "United Kingdom", "Wales"]
          },
          "_type": "spot"
        }
      ]
    }
  }
]
```

**Result types:** `spot`, `subregion`, `geoname`

**Note:** This endpoint uses a different base path (`/search/site`) rather than `/kbyg/`. Bot evasion headers are still required.

---

## Taxonomy

### GET /taxonomy (type=taxonomy)

Returns a taxonomy node with its immediate children. Used to walk the geographic hierarchy.

```
GET /taxonomy?type=taxonomy&id={taxonomyId}&maxDepth=0
```

**Parameters:**
| Param | Required | Description |
|-------|----------|-------------|
| `type` | Yes | `taxonomy` for hierarchy nodes |
| `id` | Yes | Taxonomy node ID |
| `maxDepth` | No | Depth of children to include (0 = immediate children only) |

**Response:**

```json
{
  "_id": "58f7ed51dadb30820bb38782",
  "name": "Earth",
  "type": "spot_type",
  "contains": [
    {
      "_id": "...",
      "name": "North America",
      "type": "Admin1H",
      "hasSpots": true
    }
  ],
  "location": {
    "type": "Point",
    "coordinates": [0, 0]
  },
  "associated": {
    "links": [
      { "key": "www", "href": "https://..." }
    ]
  },
  "in": []
}
```

**Key fields:**
- `contains[]` - child nodes at the next level
- `in[]` - parent nodes (geographic ancestry)
- `location.coordinates` - GeoJSON `[lng, lat]`

**Hierarchy levels:** `spot_type` (Earth) > `Admin1H` (continent) > `Country` > `Region` > `Subregion` > `spot`

**Root node:** `58f7ed51dadb30820bb38782` (Earth)

Our `taxonomy_scraper` recursively walks this tree starting from the root, with a 500ms delay between requests to avoid rate limiting.

---

### GET /taxonomy (type=spot)

Returns taxonomy data for a specific spot, including its full geographic ancestry via the `in` array.

```
GET /taxonomy?type=spot&id={spotId}&maxDepth=0
```

**Parameters:**
| Param | Required | Description |
|-------|----------|-------------|
| `type` | Yes | `spot` for spot-specific data |
| `id` | Yes | Spot ID |
| `maxDepth` | No | Depth of children (usually 0 for spots) |

**Response:**

```json
{
  "_id": "584204204e65fad6a77090d2",
  "name": "Rest Bay",
  "type": "spot",
  "location": {
    "type": "Point",
    "coordinates": [-3.8281, 51.4784]
  },
  "in": [
    { "_id": "...", "name": "Glamorgan Heritage Coast", "type": "Subregion" },
    { "_id": "...", "name": "Wales", "type": "Region" },
    { "_id": "...", "name": "United Kingdom", "type": "Country" },
    { "_id": "...", "name": "Europe", "type": "Admin1H" },
    { "_id": "58f7ed51dadb30820bb38782", "name": "Earth", "type": "spot_type" }
  ]
}
```

**Note:** The `in` array provides the complete geographic lineage without needing to walk the tree. Useful for getting a single spot's place in the hierarchy.

---

## Sitemap

### GET /sitemaps/spots.xml

XML sitemap listing all surf spots and their forecast pages. Served from `www.surfline.com`, not `services.surfline.com`.

```
GET https://www.surfline.com/sitemaps/spots.xml
```

**Response:** Standard XML sitemap with `<url><loc>` entries:

```xml
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url>
    <loc>https://www.surfline.com/surf-report/rest-bay/584204204e65fad6a77090d2</loc>
  </url>
  <url>
    <loc>https://www.surfline.com/surf-report/rest-bay/584204204e65fad6a77090d2/forecast</loc>
  </url>
</urlset>
```

Our `sitemap_scraper` parses this with `lxml`, extracting spot IDs from URLs via regex: `surfline.com/surf-report/[name]/([spot_id])(/forecast)?`

---

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

---

## Endpoints Not Found (404)

These endpoints were tested on 2026-03-06 and returned 404 - documented here to avoid re-testing:

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
| `/kbyg/spots/nearme` | Lat/lon based - use `/mapview` with bounding box instead |

---

## Quick Reference

| Category | Endpoint | We Scrape? |
|----------|----------|------------|
| Spot Data | `/kbyg/spots/reports` | Yes (spot_scraper) |
| Spot Data | `/kbyg/spots/details` | No |
| Spot Data | `/kbyg/spots/nearby` | No |
| Forecast | `/kbyg/spots/forecasts/rating` | Yes (forecast_scraper) |
| Forecast | `/kbyg/spots/forecasts/wave` | Yes (forecast_scraper) |
| Forecast | `/kbyg/spots/forecasts/wind` | Yes (forecast_scraper) |
| Forecast | `/kbyg/spots/forecasts/tides` | Yes (forecast_scraper) |
| Forecast | `/kbyg/spots/forecasts/weather` | Yes (forecast_scraper) |
| Forecast | `/kbyg/spots/forecasts/sunlight` | Yes (forecast_scraper) |
| Forecast | `/kbyg/spots/forecasts/surf` | No |
| Forecast | `/kbyg/spots/forecasts/conditions` | No |
| Region | `/kbyg/regions/overview` | No |
| Map | `/kbyg/mapview` | No |
| Search | `/search/site` | No |
| Taxonomy | `/taxonomy` (type=taxonomy) | Yes (taxonomy_scraper) |
| Taxonomy | `/taxonomy` (type=spot) | No |
| Sitemap | `/sitemaps/spots.xml` | Yes (sitemap_scraper) |
