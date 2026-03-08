# Endpoints

> **Status: PLANNED** | Not yet implemented

All 10 API endpoints. See [API Design](README.md) for design principles and [Implementation Guide](implementation-guide.md) for architecture.

## Endpoint Summary

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/spots` | GET | List all spots with search/filter |
| `/spots/{id}/forecast` | GET | Current forecast (combined view) |
| `/spots/{id}/forecast/swells` | GET | Detailed swell components |
| `/spots/{id}/forecast/daily` | GET | Aggregated daily summary |
| `/spots/{id}/forecast/best` | GET | Find optimal surf windows |
| `/forecast/compare` | GET | Compare multiple spots |
| `/forecast/discover` | GET | Find spots by region + conditions |
| `/spots/{id}/history` | GET | Historical forecast data |
| `/spots/{id}/accuracy` | GET | Forecast accuracy analysis |
| `/spots/{id}/scrapes` | GET | List available scrape timestamps |

---

## 1. Spot Catalog

```
GET /spots
```

List all spots with metadata. Supports geographic and text filtering.

### Query Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `lat` | float | - | Latitude for geographic filter |
| `lng` | float | - | Longitude for geographic filter |
| `radius` | int | 50 | Search radius in kilometers (requires lat/lng) |
| `name` | string | - | Text search on spot name |
| `limit` | int | 100 | Results per page (max 1000) |
| `cursor` | string | - | Pagination cursor |

### Response

```json
{
  "spots": [
    {
      "id": "584204204e65fad6a77090d2",
      "name": "Porthcawl - Rest Bay",
      "lat": 51.488,
      "lng": -3.728,
      "timezone": "Europe/London",
      "links": {
        "forecast": "/spots/584204204e65fad6a77090d2/forecast",
        "history": "/spots/584204204e65fad6a77090d2/history"
      }
    }
  ],
  "pagination": {
    "next_cursor": "eyJvZmZzZXQiOjEwMH0=",
    "total": 1234
  }
}
```

---

## 2. Current Forecast

```
GET /spots/{spot_id}/forecast
```

Returns the **latest** forecast for a spot with all data types combined. This is the primary endpoint for displaying current conditions.

### Query Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `types` | string | all | Comma-separated: `wave,wind,rating,tides,weather` |
| `hours` | int | 120 | Number of hours to return (max 384) |
| `start` | ISO timestamp | now | Start time for forecast window |
| `include` | string | none | Extra data: `swells,sunlight` |
| `units` | string | imperial | Unit system: `imperial` or `metric` |

### Response

```json
{
  "spot": {
    "id": "584204204e65fad6a77090d2",
    "name": "Porthcawl - Rest Bay",
    "lat": 51.488,
    "lng": -3.728,
    "timezone": "Europe/London"
  },
  "metadata": {
    "scrape_ts": "2026-01-17T14:43:39Z",
    "model_run_ts": "2026-01-17T00:00:00Z",
    "units": {
      "system": "imperial",
      "wave_height": "ft",
      "wind_speed": "mph",
      "temperature": "F",
      "tide_height": "ft"
    }
  },
  "hourly": [
    {
      "timestamp": "2026-01-17T06:00:00Z",
      "utc_offset": 0,
      "rating": {
        "key": "FAIR_TO_GOOD",
        "value": 4
      },
      "wave": {
        "surf_min": 4,
        "surf_max": 6,
        "surf_human": "Chest to overhead",
        "surf_raw_min": 4.68,
        "surf_raw_max": 5.58,
        "power": 249.56,
        "optimal_score": 2
      },
      "wind": {
        "speed": 9.3,
        "gust": 13.2,
        "direction": 129.8,
        "direction_type": "Offshore",
        "optimal_score": 0
      },
      "weather": {
        "temperature": 43,
        "condition": "NIGHT_BRIEF_SHOWERS_POSSIBLE",
        "pressure": 1007
      }
    }
  ],
  "tides": [
    {
      "timestamp": "2026-01-17T05:24:22Z",
      "type": "HIGH",
      "height": 8.52
    },
    {
      "timestamp": "2026-01-17T10:50:35Z",
      "type": "LOW",
      "height": 2.58
    }
  ],
  "sunlight": [
    {
      "date": "2026-01-17",
      "dawn": "2026-01-17T07:21:48Z",
      "sunrise": "2026-01-17T07:53:24Z",
      "sunset": "2026-01-17T17:05:18Z",
      "dusk": "2026-01-17T17:36:54Z"
    }
  ]
}
```

### With Embedded Swells

When `?include=swells` is specified, each hourly entry includes swell components:

```json
{
  "timestamp": "2026-01-17T06:00:00Z",
  "wave": {
    "surf_min": 4,
    "surf_max": 6,
    "power": 249.56
  },
  "swells": [
    {
      "index": 1,
      "active": true,
      "height": 3.45,
      "period": 10,
      "direction": 248.6,
      "direction_min": 236.7,
      "impact": 0.49,
      "power": 96.7,
      "optimal_score": 1
    }
  ]
}
```

All 6 swell components are returned with an `active` flag. Inactive swells have `height: 0`.

---

## 3. Swells Detail

```
GET /spots/{spot_id}/forecast/swells
```

Returns detailed swell components for wave analysis.

### Query Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `hours` | int | 120 | Number of hours to return |
| `active_only` | boolean | false | Filter to only active swells (height > 0) |

### Response

```json
{
  "spot_id": "584204204e65fad6a77090d2",
  "metadata": {
    "scrape_ts": "2026-01-17T14:43:39Z",
    "units": { "height": "ft", "direction": "degrees" }
  },
  "swells": [
    {
      "timestamp": "2026-01-17T06:00:00Z",
      "components": [
        {
          "index": 1,
          "height": 3.45,
          "period": 10,
          "direction": 248.6,
          "direction_min": 236.7,
          "impact": 0.49,
          "power": 96.7,
          "optimal_score": 1
        }
      ]
    }
  ]
}
```

---

## 4. Daily Summary

```
GET /spots/{spot_id}/forecast/daily
```

Aggregated daily conditions for at-a-glance planning.

### Query Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `days` | int | 5 | Number of days to return (max 16) |
| `units` | string | imperial | Unit system: `imperial` or `metric` |

### Response

```json
{
  "spot_id": "584204204e65fad6a77090d2",
  "days": [
    {
      "date": "2026-01-17",
      "sunrise": "07:53",
      "sunset": "17:05",
      "daylight_hours": 9.2,
      "rating": {
        "best": "GOOD",
        "average": 3.8,
        "peak_hour": "2026-01-17T10:00:00Z"
      },
      "wave": {
        "min_range": [3, 5],
        "max_range": [5, 7],
        "peak_hour": "2026-01-17T14:00:00Z",
        "dominant_swell_direction": 248,
        "dominant_swell_period": 12
      },
      "wind": {
        "morning_type": "Offshore",
        "afternoon_type": "Onshore",
        "glassy_hours": 4,
        "avg_speed": 8.5
      },
      "tides": {
        "high": [
          { "time": "05:24", "height": 8.52 },
          { "time": "17:42", "height": 8.89 }
        ],
        "low": [
          { "time": "10:50", "height": 2.58 }
        ]
      },
      "best_window": {
        "start": "2026-01-17T07:00:00Z",
        "end": "2026-01-17T10:00:00Z",
        "reason": "Offshore winds, rising tide, good swell"
      }
    }
  ]
}
```

---

## 5. Best Conditions Finder

```
GET /spots/{spot_id}/forecast/best
```

Find optimal surf windows based on specified criteria.

### Query Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `min_surf` | float | - | Minimum wave height (ft or m based on units) |
| `max_surf` | float | - | Maximum wave height |
| `max_wind` | float | - | Maximum wind speed (mph or km/h) |
| `wind_type` | string | any | Preferred wind: `offshore`, `cross-offshore`, `any` |
| `min_rating` | int | - | Minimum rating value (0-6) |
| `daylight_only` | boolean | true | Only return windows during daylight |
| `min_period` | int | - | Minimum swell period (seconds) |
| `min_duration` | int | 2 | Minimum window duration (hours) |
| `units` | string | imperial | Unit system |

### Response

```json
{
  "spot_id": "584204204e65fad6a77090d2",
  "criteria": {
    "min_surf": 3,
    "max_wind": 15,
    "wind_type": "offshore",
    "min_rating": 3,
    "daylight_only": true
  },
  "windows": [
    {
      "start": "2026-01-17T07:00:00Z",
      "end": "2026-01-17T11:00:00Z",
      "duration_hours": 4,
      "avg_rating": 4.2,
      "conditions": {
        "surf_range": [4, 6],
        "wind_avg": 8.5,
        "wind_type": "Offshore",
        "tide_trend": "rising",
        "swell_period": 12
      },
      "score": 87
    }
  ]
}
```

### Score Calculation

The `score` (0-100) is computed based on:

| Factor | Weight | Scoring |
|--------|--------|---------|
| Rating | 30% | Linear scale from min_rating to 6 |
| Wind | 25% | Offshore=100, Cross-offshore=75, Cross-shore=50, etc. |
| Swell period | 20% | Higher periods score better |
| Duration | 15% | Longer windows score better |
| Tide phase | 10% | Mid-tide windows preferred |

---

## 6. Multi-Spot Comparison

```
GET /forecast/compare
```

Compare multiple spots for the same time window.

### Query Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `spots` | string | required | Comma-separated spot IDs (max 10) |
| `timestamp` | ISO timestamp | - | Specific hour to compare |
| `date` | date | - | Compare best conditions for a date |
| `units` | string | imperial | Unit system |

**Note:** Either `timestamp` or `date` must be provided, not both.

### Response (timestamp mode)

```json
{
  "timestamp": "2026-01-17T10:00:00Z",
  "spots": [
    {
      "spot": { "id": "584204204e65fad6a77090d2", "name": "Porthcawl - Rest Bay" },
      "rating": { "key": "GOOD", "value": 4 },
      "wave": { "surf_min": 4, "surf_max": 6, "power": 245.3 },
      "wind": { "speed": 8, "direction_type": "Offshore" },
      "rank": 1
    }
  ]
}
```

---

## 7. Regional Discovery

```
GET /forecast/discover
```

Find spots with good conditions in a geographic region.

### Query Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `lat` | float | required | Center latitude |
| `lng` | float | required | Center longitude |
| `radius` | int | 50 | Search radius in kilometers |
| `min_rating` | int | - | Minimum rating value |
| `min_surf` | float | - | Minimum wave height |
| `date` | date | today | Target date |
| `sort` | string | rating | Sort by: `rating`, `distance`, `wave_height` |
| `limit` | int | 20 | Maximum results |
| `units` | string | imperial | Unit system |

### Response

```json
{
  "center": { "lat": 51.5, "lng": -3.5 },
  "radius_km": 50,
  "date": "2026-01-17",
  "spots": [
    {
      "spot": {
        "id": "584204204e65fad6a77090d2",
        "name": "Porthcawl - Rest Bay",
        "lat": 51.488,
        "lng": -3.728,
        "distance_km": 12.3
      },
      "best_window": {
        "start": "2026-01-17T07:00:00Z",
        "end": "2026-01-17T11:00:00Z",
        "rating": 4,
        "surf_range": [4, 6],
        "wind_type": "Offshore"
      }
    }
  ]
}
```

---

## 8. Forecast History

```
GET /spots/{spot_id}/history
```

Access past forecasts for analysis. Supports historical conditions lookup and "time machine" queries.

### Query Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `from` | ISO date | required | Start date |
| `to` | ISO date | required | End date |
| `types` | string | all | Forecast types to include |
| `resolution` | string | hourly | `hourly` or `daily` (aggregated) |
| `scrape_ts` | ISO timestamp | - | Specific scrape timestamp (time machine mode) |
| `units` | string | imperial | Unit system |

### Use Cases

**A. Historical conditions (what actually happened):**
```
GET /spots/{id}/history?from=2026-01-01&to=2026-01-07&resolution=daily
```

**B. Time machine (what did the forecast say then):**
```
GET /spots/{id}/history?scrape_ts=2026-01-15T14:00:00Z
```

---

## 9. Forecast Accuracy

```
GET /spots/{spot_id}/accuracy
```

Compare what was forecasted vs what happened.

### Query Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `target_date` | ISO date | required | The date to analyze |
| `lead_times` | string | 1,2,3,5 | Days before to compare (comma-separated) |

### Response

```json
{
  "spot_id": "584204204e65fad6a77090d2",
  "target_date": "2026-01-15",
  "actual": {
    "rating_avg": 4.2,
    "wave_avg": [4.5, 6.2],
    "wind_avg": 8.3
  },
  "forecasts": [
    {
      "lead_time_days": 1,
      "scrape_ts": "2026-01-14T14:00:00Z",
      "predicted": {
        "rating_avg": 4.0,
        "wave_avg": [4.3, 6.0],
        "wind_avg": 9.1
      },
      "error": {
        "rating_mae": 0.2,
        "wave_mae": 0.2,
        "wind_mae": 0.8
      }
    }
  ]
}
```

---

## 10. Scrape Versions

```
GET /spots/{spot_id}/scrapes
```

List available scrape timestamps for a spot.

### Query Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `from` | ISO date | 30 days ago | Start date |
| `to` | ISO date | today | End date |
| `limit` | int | 100 | Maximum results |

### Response

```json
{
  "spot_id": "584204204e65fad6a77090d2",
  "scrapes": [
    {
      "scrape_ts": "2026-01-17T14:43:39Z",
      "model_run_ts": "2026-01-17T00:00:00Z",
      "forecast_range": {
        "from": "2026-01-17T00:00:00Z",
        "to": "2026-01-22T00:00:00Z"
      }
    }
  ]
}
```

---

## Query Parameters Reference

### Common Parameters

| Parameter | Type | Default | Description | Endpoints |
|-----------|------|---------|-------------|-----------|
| `units` | string | imperial | `imperial` or `metric` | All |
| `limit` | int | varies | Results per page | List endpoints |
| `cursor` | string | - | Pagination cursor | List endpoints |

### Time Parameters

| Parameter | Type | Format | Description |
|-----------|------|--------|-------------|
| `timestamp` | string | ISO 8601 | Specific point in time |
| `date` | string | ISO 8601 date | Specific date |
| `from` | string | ISO 8601 date | Range start |
| `to` | string | ISO 8601 date | Range end |
| `hours` | int | - | Duration in hours |
| `days` | int | - | Duration in days |

### Filter Parameters

| Parameter | Type | Range | Description |
|-----------|------|-------|-------------|
| `min_surf` | float | 0-30 | Minimum wave height |
| `max_surf` | float | 0-30 | Maximum wave height |
| `max_wind` | float | 0-100 | Maximum wind speed |
| `min_rating` | int | 0-6 | Minimum rating value |
| `min_period` | int | 1-25 | Minimum swell period (seconds) |
| `wind_type` | string | enum | `offshore`, `cross-offshore`, `cross-shore`, `cross-onshore`, `onshore`, `any` |

---

## Response Schemas

### Spot Object

```typescript
interface Spot {
  id: string;           // Surfline spot ID
  name: string;         // Human-readable name
  lat: number;          // Latitude
  lng: number;          // Longitude
  timezone: string;     // IANA timezone (e.g., "Europe/London")
  links?: {
    forecast: string;
    history: string;
  };
}
```

### Metadata Object

```typescript
interface Metadata {
  scrape_ts: string;      // ISO timestamp when forecast was scraped
  model_run_ts: string;   // ISO timestamp of model initialization
  units: {
    system: "imperial" | "metric";
    wave_height: "ft" | "m";
    wind_speed: "mph" | "km/h";
    temperature: "F" | "C";
    tide_height: "ft" | "m";
  };
}
```

### Enum Values

**RatingKey:**
```
FLAT, VERY_POOR, POOR, POOR_TO_FAIR, FAIR, FAIR_TO_GOOD, GOOD, EPIC
```

**WindType:**
```
Offshore, Cross-offshore, Cross-shore, Cross-onshore, Onshore
```

**WeatherCondition (examples):**
```
NIGHT_CLEAR, NIGHT_BRIEF_SHOWERS_POSSIBLE, DAWN_CLEAR, DAY_PARTLY_CLOUDY,
DAY_SUNNY, DAY_CLOUDY, DAY_RAIN, DUSK_CLEAR, etc.
```

---

## Error Handling

### Error Response Format

```json
{
  "error": {
    "code": "SPOT_NOT_FOUND",
    "message": "Spot with ID 'abc123' not found",
    "details": { "spot_id": "abc123" }
  }
}
```

### Error Codes

| Code | HTTP Status | Description |
|------|-------------|-------------|
| `SPOT_NOT_FOUND` | 404 | Invalid spot ID |
| `INVALID_DATE_RANGE` | 400 | Date range too large or invalid format |
| `INVALID_PARAMETER` | 400 | Invalid query parameter value |
| `NO_DATA_AVAILABLE` | 404 | No forecast data for requested period |
| `RATE_LIMITED` | 429 | Too many requests |
| `INTERNAL_ERROR` | 500 | Server error |

---

## Pagination and Caching

### Cursor-Based Pagination

```json
{
  "spots": [...],
  "pagination": {
    "next_cursor": "eyJvZmZzZXQiOjEwMH0=",
    "prev_cursor": "eyJvZmZzZXQiOjB9",
    "total": 1234
  }
}
```

### Page Size Limits

| Endpoint | Default | Maximum |
|----------|---------|---------|
| `/spots` | 100 | 1000 |
| `/spots/{id}/scrapes` | 100 | 500 |
| `/forecast/discover` | 20 | 100 |

### Cache Durations

| Data Type | Cache Duration | Rationale |
|-----------|----------------|-----------|
| Current forecast | 30 minutes | Scrapes happen ~every 6 hours |
| Spot metadata | 24 hours | Rarely changes |
| Historical data | 1 year | Immutable |
| Accuracy analysis | 24 hours | Computed aggregates |
