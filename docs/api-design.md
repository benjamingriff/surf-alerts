# Surf Forecast API Design

This document describes the design of the Surf Forecast API, which serves both current forecasts and historical data from the normalized Parquet data model. It covers API endpoints, request/response schemas, authentication, caching, and implementation guidance.

---

## Table of Contents

1. [Overview](#overview)
2. [Core Design Principles](#core-design-principles)
3. [Data Shape Philosophy](#data-shape-philosophy)
4. [API Endpoints](#api-endpoints)
   - [Spot Catalog](#1-spot-catalog)
   - [Current Forecast](#2-current-forecast)
   - [Swells Detail](#3-swells-detail)
   - [Daily Summary](#4-daily-summary)
   - [Best Conditions Finder](#5-best-conditions-finder)
   - [Multi-Spot Comparison](#6-multi-spot-comparison)
   - [Regional Discovery](#7-regional-discovery)
   - [Forecast History](#8-forecast-history)
   - [Forecast Accuracy](#9-forecast-accuracy)
   - [Scrape Versions](#10-scrape-versions)
5. [Query Parameters Reference](#query-parameters-reference)
6. [Response Schemas](#response-schemas)
7. [Unit Conversion](#unit-conversion)
8. [Pagination and Caching](#pagination-and-caching)
9. [Error Handling](#error-handling)
10. [Authentication and Rate Limiting](#authentication-and-rate-limiting)
11. [Database Architecture](#database-architecture)
12. [Implementation Recommendations](#implementation-recommendations)
13. [Verification Plan](#verification-plan)

---

## Overview

### Purpose

The Surf Forecast API provides programmatic access to surf condition data, enabling:

- **Single-spot forecasts** - Detailed hourly predictions for a specific beach
- **Multi-spot discovery** - Find the best conditions across a region
- **Session planning** - Identify optimal surf windows based on criteria
- **Forecast accuracy analysis** - Compare predictions against actual conditions

### Use Cases

| Consumer | Primary Endpoints | Use Case |
|----------|-------------------|----------|
| Mobile app | `/spots/{id}/forecast` | Display current conditions |
| Trip planner | `/forecast/discover` | Find best spots for upcoming weekend |
| Data analyst | `/spots/{id}/history`, `/spots/{id}/accuracy` | Forecast model evaluation |
| Alert system | `/spots/{id}/forecast/best` | Notify when conditions match preferences |

---

## Core Design Principles

### 1. Resource-Oriented

Spots are the primary resource. Forecasts are sub-resources of spots.

```
/spots                          → List all spots
/spots/{id}                     → Spot metadata
/spots/{id}/forecast            → Current forecast for spot
/spots/{id}/forecast/swells     → Detailed swell data
/spots/{id}/forecast/daily      → Aggregated daily view
/spots/{id}/forecast/best       → Optimal surf windows
/spots/{id}/history             → Historical forecasts
/spots/{id}/accuracy            → Forecast accuracy metrics
/spots/{id}/scrapes             → Available scrape timestamps
```

### 2. Composable

Clients can request specific forecast types or combined views:

```
GET /spots/{id}/forecast?types=wave,wind           → Only wave and wind
GET /spots/{id}/forecast?types=wave&include=swells → Wave with embedded swells
GET /spots/{id}/forecast                           → All types combined
```

### 3. Time-Aware

Clear distinction between two temporal concepts:

| Concept | Description | Use Case |
|---------|-------------|----------|
| `forecast_ts` | The time being predicted | "What are conditions at 10am tomorrow?" |
| `scrape_ts` | When the prediction was made | "What did yesterday's forecast say about today?" |

### 4. Cache-Friendly

- ETags based on `scrape_ts` for efficient conditional requests
- Immutable historical data can be cached indefinitely
- Current forecasts cached for 30 minutes (scrapes occur ~every 6 hours)

---

## Data Shape Philosophy

### The "Session" Concept

Surfers think in **sessions** - a window of time when conditions align. The API supports both:

1. **Raw time-series** - Hourly data points per forecast type
2. **Session views** - Aggregated windows with combined conditions

### Forecast Type Characteristics

| Forecast Type | Time Range | Granularity | API Strategy |
|---------------|------------|-------------|--------------|
| Rating | 5 days | Hourly | Core endpoint, `hourly[]` array |
| Wave | 5 days | Hourly | Core endpoint, `hourly[]` array |
| Wind | 5 days | Hourly | Core endpoint, `hourly[]` array |
| Tides | 6 days | Irregular | Separate `tides[]` array (event-based) |
| Weather | 16 days | Hourly | Extended endpoint available |
| Sunlight | 16 days | Daily | Included in `sunlight[]` array |

### Why Tides Are Separate

Tides are **event-based**, not hourly intervals. HIGH and LOW events occur at irregular times:

```json
{
  "hourly": [
    { "timestamp": "2026-01-17T06:00:00Z", "wave": {...}, "wind": {...} },
    { "timestamp": "2026-01-17T07:00:00Z", "wave": {...}, "wind": {...} }
  ],
  "tides": [
    { "timestamp": "2026-01-17T05:24:22Z", "type": "HIGH", "height": 8.52 },
    { "timestamp": "2026-01-17T10:50:35Z", "type": "LOW", "height": 2.58 }
  ]
}
```

---

## API Endpoints

### 1. Spot Catalog

```
GET /spots
```

List all spots with metadata. Supports geographic and text filtering.

#### Query Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `lat` | float | - | Latitude for geographic filter |
| `lng` | float | - | Longitude for geographic filter |
| `radius` | int | 50 | Search radius in kilometers (requires lat/lng) |
| `name` | string | - | Text search on spot name |
| `limit` | int | 100 | Results per page (max 1000) |
| `cursor` | string | - | Pagination cursor |

#### Response

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
    },
    {
      "id": "5842041f4e65fad6a7708814",
      "name": "Croyde Beach",
      "lat": 51.131,
      "lng": -4.243,
      "timezone": "Europe/London",
      "links": {
        "forecast": "/spots/5842041f4e65fad6a7708814/forecast",
        "history": "/spots/5842041f4e65fad6a7708814/history"
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

### 2. Current Forecast

```
GET /spots/{spot_id}/forecast
```

Returns the **latest** forecast for a spot with all data types combined. This is the primary endpoint for displaying current conditions.

#### Path Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `spot_id` | string | Surfline spot identifier |

#### Query Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `types` | string | all | Comma-separated: `wave,wind,rating,tides,weather` |
| `hours` | int | 120 | Number of hours to return (max 384) |
| `start` | ISO timestamp | now | Start time for forecast window |
| `include` | string | none | Extra data: `swells,sunlight` |
| `units` | string | imperial | Unit system: `imperial` or `metric` |

#### Response

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
      "tide_height": "m"
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
    },
    {
      "timestamp": "2026-01-17T07:00:00Z",
      "utc_offset": 0,
      "rating": {
        "key": "GOOD",
        "value": 4
      },
      "wave": {
        "surf_min": 4,
        "surf_max": 6,
        "surf_human": "Chest to overhead",
        "surf_raw_min": 4.52,
        "surf_raw_max": 5.41,
        "power": 241.23,
        "optimal_score": 2
      },
      "wind": {
        "speed": 7.8,
        "gust": 11.5,
        "direction": 135.2,
        "direction_type": "Offshore",
        "optimal_score": 1
      },
      "weather": {
        "temperature": 42,
        "condition": "DAWN_CLEAR",
        "pressure": 1008
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
    },
    {
      "timestamp": "2026-01-17T17:42:18Z",
      "type": "HIGH",
      "height": 8.89
    }
  ],
  "sunlight": [
    {
      "date": "2026-01-17",
      "dawn": "2026-01-17T07:21:48Z",
      "sunrise": "2026-01-17T07:53:24Z",
      "sunset": "2026-01-17T17:05:18Z",
      "dusk": "2026-01-17T17:36:54Z"
    },
    {
      "date": "2026-01-18",
      "dawn": "2026-01-18T07:20:42Z",
      "sunrise": "2026-01-18T07:52:15Z",
      "sunset": "2026-01-18T17:06:48Z",
      "dusk": "2026-01-18T17:38:21Z"
    }
  ]
}
```

#### With Embedded Swells

When `?include=swells` is specified, each hourly entry includes swell components:

```json
{
  "timestamp": "2026-01-17T06:00:00Z",
  "wave": {
    "surf_min": 4,
    "surf_max": 6,
    "surf_human": "Chest to overhead",
    "surf_raw_min": 4.68,
    "surf_raw_max": 5.58,
    "power": 249.56,
    "optimal_score": 2
  },
  "swells": [
    {
      "index": 0,
      "active": false,
      "height": 0,
      "period": 0,
      "direction": 0,
      "direction_min": 0,
      "impact": 0,
      "power": 0,
      "optimal_score": 0
    },
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
    },
    {
      "index": 2,
      "active": true,
      "height": 2.79,
      "period": 15,
      "direction": 248.7,
      "direction_min": 244.2,
      "impact": 0.51,
      "power": 152.9,
      "optimal_score": 1
    },
    {
      "index": 3,
      "active": false,
      "height": 0,
      "period": 0,
      "direction": 0,
      "direction_min": 0,
      "impact": 0,
      "power": 0,
      "optimal_score": 0
    },
    {
      "index": 4,
      "active": false,
      "height": 0,
      "period": 0,
      "direction": 0,
      "direction_min": 0,
      "impact": 0,
      "power": 0,
      "optimal_score": 0
    },
    {
      "index": 5,
      "active": false,
      "height": 0,
      "period": 0,
      "direction": 0,
      "direction_min": 0,
      "impact": 0,
      "power": 0,
      "optimal_score": 0
    }
  ]
}
```

**Note:** All 6 swell components are returned with an `active` flag. Inactive swells have `height: 0`. This preserves the complete data structure while making it easy for clients to filter.

---

### 3. Swells Detail

```
GET /spots/{spot_id}/forecast/swells
```

Returns detailed swell components for wave analysis. Use this endpoint when you need comprehensive swell data without the full forecast.

#### Query Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `hours` | int | 120 | Number of hours to return |
| `active_only` | boolean | false | Filter to only active swells (height > 0) |

#### Response

```json
{
  "spot_id": "584204204e65fad6a77090d2",
  "metadata": {
    "scrape_ts": "2026-01-17T14:43:39Z",
    "units": {
      "height": "ft",
      "direction": "degrees"
    }
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
        },
        {
          "index": 2,
          "height": 2.79,
          "period": 15,
          "direction": 248.7,
          "direction_min": 244.2,
          "impact": 0.51,
          "power": 152.9,
          "optimal_score": 1
        }
      ]
    },
    {
      "timestamp": "2026-01-17T07:00:00Z",
      "components": [
        {
          "index": 1,
          "height": 3.38,
          "period": 10,
          "direction": 249.1,
          "direction_min": 237.2,
          "impact": 0.47,
          "power": 94.2,
          "optimal_score": 1
        },
        {
          "index": 2,
          "height": 2.82,
          "period": 15,
          "direction": 248.9,
          "direction_min": 244.5,
          "impact": 0.53,
          "power": 155.1,
          "optimal_score": 1
        }
      ]
    }
  ]
}
```

---

### 4. Daily Summary

```
GET /spots/{spot_id}/forecast/daily
```

Aggregated daily conditions for at-a-glance planning. Returns computed summaries including best windows, average conditions, and tide schedules.

#### Query Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `days` | int | 5 | Number of days to return (max 16) |
| `units` | string | imperial | Unit system: `imperial` or `metric` |

#### Response

```json
{
  "spot_id": "584204204e65fad6a77090d2",
  "metadata": {
    "scrape_ts": "2026-01-17T14:43:39Z",
    "units": {
      "system": "imperial",
      "wave_height": "ft",
      "wind_speed": "mph",
      "temperature": "F"
    }
  },
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
    },
    {
      "date": "2026-01-18",
      "sunrise": "07:52",
      "sunset": "17:06",
      "daylight_hours": 9.2,
      "rating": {
        "best": "FAIR_TO_GOOD",
        "average": 3.5,
        "peak_hour": "2026-01-18T08:00:00Z"
      },
      "wave": {
        "min_range": [3, 4],
        "max_range": [4, 6],
        "peak_hour": "2026-01-18T12:00:00Z",
        "dominant_swell_direction": 252,
        "dominant_swell_period": 11
      },
      "wind": {
        "morning_type": "Offshore",
        "afternoon_type": "Cross-onshore",
        "glassy_hours": 3,
        "avg_speed": 10.2
      },
      "tides": {
        "high": [
          { "time": "06:15", "height": 8.31 },
          { "time": "18:28", "height": 8.65 }
        ],
        "low": [
          { "time": "11:42", "height": 2.72 }
        ]
      },
      "best_window": {
        "start": "2026-01-18T06:30:00Z",
        "end": "2026-01-18T09:00:00Z",
        "reason": "Light offshore winds, mid-tide"
      }
    }
  ]
}
```

---

### 5. Best Conditions Finder

```
GET /spots/{spot_id}/forecast/best
```

Find optimal surf windows based on specified criteria. Returns ranked time windows that meet all filter conditions.

#### Query Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `min_surf` | float | - | Minimum wave height (ft or m based on units) |
| `max_surf` | float | - | Maximum wave height |
| `max_wind` | float | - | Maximum wind speed (mph or km/h) |
| `wind_type` | string | any | Preferred wind: `offshore`, `cross-offshore`, `any` |
| `min_rating` | int | - | Minimum rating value (1-5) |
| `daylight_only` | boolean | true | Only return windows during daylight |
| `min_period` | int | - | Minimum swell period (seconds) |
| `min_duration` | int | 2 | Minimum window duration (hours) |
| `units` | string | imperial | Unit system |

#### Response

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
    },
    {
      "start": "2026-01-18T06:00:00Z",
      "end": "2026-01-18T09:00:00Z",
      "duration_hours": 3,
      "avg_rating": 3.8,
      "conditions": {
        "surf_range": [3, 5],
        "wind_avg": 6.2,
        "wind_type": "Offshore",
        "tide_trend": "falling",
        "swell_period": 11
      },
      "score": 72
    },
    {
      "start": "2026-01-19T07:30:00Z",
      "end": "2026-01-19T10:30:00Z",
      "duration_hours": 3,
      "avg_rating": 3.5,
      "conditions": {
        "surf_range": [3, 4],
        "wind_avg": 9.1,
        "wind_type": "Cross-offshore",
        "tide_trend": "rising",
        "swell_period": 10
      },
      "score": 65
    }
  ]
}
```

#### Score Calculation

The `score` (0-100) is computed based on:

| Factor | Weight | Scoring |
|--------|--------|---------|
| Rating | 30% | Linear scale from min_rating to 5 |
| Wind | 25% | Offshore=100, Cross-offshore=75, Crosswind=50, etc. |
| Swell period | 20% | Higher periods score better |
| Duration | 15% | Longer windows score better |
| Tide phase | 10% | Mid-tide windows preferred |

---

### 6. Multi-Spot Comparison

```
GET /forecast/compare
```

Compare multiple spots for the same time window. Useful for deciding between nearby beaches.

#### Query Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `spots` | string | required | Comma-separated spot IDs (max 10) |
| `timestamp` | ISO timestamp | - | Specific hour to compare |
| `date` | date | - | Compare best conditions for a date |
| `units` | string | imperial | Unit system |

**Note:** Either `timestamp` or `date` must be provided, not both.

#### Response (timestamp mode)

```json
{
  "timestamp": "2026-01-17T10:00:00Z",
  "spots": [
    {
      "spot": {
        "id": "584204204e65fad6a77090d2",
        "name": "Porthcawl - Rest Bay"
      },
      "rating": { "key": "GOOD", "value": 4 },
      "wave": { "surf_min": 4, "surf_max": 6, "power": 245.3 },
      "wind": { "speed": 8, "direction_type": "Offshore" },
      "rank": 1
    },
    {
      "spot": {
        "id": "5842041f4e65fad6a7708814",
        "name": "Croyde Beach"
      },
      "rating": { "key": "FAIR_TO_GOOD", "value": 3 },
      "wave": { "surf_min": 3, "surf_max": 5, "power": 198.7 },
      "wind": { "speed": 12, "direction_type": "Cross-onshore" },
      "rank": 2
    },
    {
      "spot": {
        "id": "5842041f4e65fad6a7708901",
        "name": "Woolacombe"
      },
      "rating": { "key": "FAIR", "value": 3 },
      "wave": { "surf_min": 3, "surf_max": 4, "power": 165.2 },
      "wind": { "speed": 14, "direction_type": "Onshore" },
      "rank": 3
    }
  ]
}
```

#### Response (date mode)

When `date` is provided, compares the best window for each spot:

```json
{
  "date": "2026-01-17",
  "spots": [
    {
      "spot": {
        "id": "584204204e65fad6a77090d2",
        "name": "Porthcawl - Rest Bay"
      },
      "best_window": {
        "start": "2026-01-17T07:00:00Z",
        "end": "2026-01-17T11:00:00Z",
        "avg_rating": 4.2,
        "surf_range": [4, 6],
        "wind_type": "Offshore"
      },
      "rank": 1
    },
    {
      "spot": {
        "id": "5842041f4e65fad6a7708814",
        "name": "Croyde Beach"
      },
      "best_window": {
        "start": "2026-01-17T06:30:00Z",
        "end": "2026-01-17T09:00:00Z",
        "avg_rating": 3.5,
        "surf_range": [3, 5],
        "wind_type": "Offshore"
      },
      "rank": 2
    }
  ]
}
```

---

### 7. Regional Discovery

```
GET /forecast/discover
```

Find spots with good conditions in a geographic region. Useful for trip planning when you're flexible on location.

#### Query Parameters

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

#### Response

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
    },
    {
      "spot": {
        "id": "584204204e65fad6a77090d5",
        "name": "Ogmore-by-Sea",
        "lat": 51.462,
        "lng": -3.639,
        "distance_km": 8.7
      },
      "best_window": {
        "start": "2026-01-17T08:00:00Z",
        "end": "2026-01-17T10:00:00Z",
        "rating": 3,
        "surf_range": [3, 5],
        "wind_type": "Cross-offshore"
      }
    }
  ]
}
```

---

### 8. Forecast History

```
GET /spots/{spot_id}/history
```

Access past forecasts for analysis. Supports both historical conditions lookup and "time machine" queries.

#### Query Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `from` | ISO date | required | Start date |
| `to` | ISO date | required | End date |
| `types` | string | all | Forecast types to include |
| `resolution` | string | hourly | `hourly` or `daily` (aggregated) |
| `scrape_ts` | ISO timestamp | - | Specific scrape timestamp (time machine mode) |
| `units` | string | imperial | Unit system |

#### Use Cases

**A. Historical conditions (what actually happened):**

```
GET /spots/{id}/history?from=2026-01-01&to=2026-01-07&resolution=daily
```

**B. Time machine (what did the forecast say then):**

```
GET /spots/{id}/history?scrape_ts=2026-01-15T14:00:00Z
```

Returns the forecast as it existed on Jan 15 (looking forward from that scrape).

#### Response (daily resolution)

```json
{
  "spot_id": "584204204e65fad6a77090d2",
  "period": {
    "from": "2026-01-01",
    "to": "2026-01-07"
  },
  "resolution": "daily",
  "data": [
    {
      "date": "2026-01-01",
      "rating_avg": 3.5,
      "rating_best": "GOOD",
      "wave_avg_min": 3.2,
      "wave_avg_max": 4.8,
      "wave_peak_min": 4,
      "wave_peak_max": 6,
      "wind_avg_speed": 12.3,
      "wind_dominant_type": "Cross-onshore"
    },
    {
      "date": "2026-01-02",
      "rating_avg": 4.1,
      "rating_best": "GOOD",
      "wave_avg_min": 4.5,
      "wave_avg_max": 6.2,
      "wave_peak_min": 5,
      "wave_peak_max": 7,
      "wind_avg_speed": 8.7,
      "wind_dominant_type": "Offshore"
    }
  ]
}
```

#### Response (time machine mode)

```json
{
  "spot_id": "584204204e65fad6a77090d2",
  "scrape_ts": "2026-01-15T14:00:00Z",
  "model_run_ts": "2026-01-15T00:00:00Z",
  "forecast_range": {
    "from": "2026-01-15T00:00:00Z",
    "to": "2026-01-20T00:00:00Z"
  },
  "hourly": [
    {
      "timestamp": "2026-01-15T14:00:00Z",
      "rating": { "key": "FAIR_TO_GOOD", "value": 4 },
      "wave": { "surf_min": 3, "surf_max": 5 },
      "wind": { "speed": 10.2, "direction_type": "Cross-offshore" }
    }
  ]
}
```

---

### 9. Forecast Accuracy

```
GET /spots/{spot_id}/accuracy
```

Compare what was forecasted vs what happened. Essential for understanding forecast reliability at different lead times.

#### Query Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `target_date` | ISO date | required | The date to analyze |
| `lead_times` | string | 1,2,3,5 | Days before to compare (comma-separated) |

#### Response

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
    },
    {
      "lead_time_days": 2,
      "scrape_ts": "2026-01-13T14:00:00Z",
      "predicted": {
        "rating_avg": 3.8,
        "wave_avg": [4.0, 5.5],
        "wind_avg": 10.5
      },
      "error": {
        "rating_mae": 0.4,
        "wave_mae": 0.6,
        "wind_mae": 2.2
      }
    },
    {
      "lead_time_days": 3,
      "scrape_ts": "2026-01-12T14:00:00Z",
      "predicted": {
        "rating_avg": 3.5,
        "wave_avg": [3.5, 5.0],
        "wind_avg": 12.0
      },
      "error": {
        "rating_mae": 0.7,
        "wave_mae": 1.1,
        "wind_mae": 3.7
      }
    },
    {
      "lead_time_days": 5,
      "scrape_ts": "2026-01-10T14:00:00Z",
      "predicted": {
        "rating_avg": 3.0,
        "wave_avg": [3.0, 4.5],
        "wind_avg": 14.0
      },
      "error": {
        "rating_mae": 1.2,
        "wave_mae": 1.6,
        "wind_mae": 5.7
      }
    }
  ],
  "summary": {
    "most_accurate_lead_time": 1,
    "avg_rating_error_by_lead_time": {
      "1": 0.2,
      "2": 0.4,
      "3": 0.7,
      "5": 1.2
    }
  }
}
```

#### Error Metrics

| Metric | Description |
|--------|-------------|
| `rating_mae` | Mean Absolute Error for rating values |
| `wave_mae` | Mean Absolute Error for surf height (averaged across min/max) |
| `wind_mae` | Mean Absolute Error for wind speed |

---

### 10. Scrape Versions

```
GET /spots/{spot_id}/scrapes
```

List available scrape timestamps for a spot. Useful for understanding data freshness and accessing specific historical snapshots.

#### Query Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `from` | ISO date | 30 days ago | Start date |
| `to` | ISO date | today | End date |
| `limit` | int | 100 | Maximum results |

#### Response

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
    },
    {
      "scrape_ts": "2026-01-17T08:43:39Z",
      "model_run_ts": "2026-01-17T00:00:00Z",
      "forecast_range": {
        "from": "2026-01-17T00:00:00Z",
        "to": "2026-01-22T00:00:00Z"
      }
    },
    {
      "scrape_ts": "2026-01-17T02:43:39Z",
      "model_run_ts": "2026-01-16T12:00:00Z",
      "forecast_range": {
        "from": "2026-01-16T12:00:00Z",
        "to": "2026-01-21T12:00:00Z"
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
| `timestamp` | string | ISO 8601 | Specific point in time (`2026-01-17T10:00:00Z`) |
| `date` | string | ISO 8601 date | Specific date (`2026-01-17`) |
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
| `min_rating` | int | 1-5 | Minimum rating value |
| `min_period` | int | 1-25 | Minimum swell period (seconds) |
| `wind_type` | string | enum | `offshore`, `cross-offshore`, `crosswind`, `cross-onshore`, `onshore`, `any` |

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
    forecast: string;   // URL to forecast endpoint
    history: string;    // URL to history endpoint
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
    tide_height: "m";
  };
}
```

### Hourly Entry Object

```typescript
interface HourlyEntry {
  timestamp: string;      // ISO timestamp
  utc_offset: number;     // Hours from UTC

  rating?: {
    key: RatingKey;       // "FAIR", "GOOD", "FAIR_TO_GOOD", etc.
    value: number;        // 1-5
  };

  wave?: {
    surf_min: number;     // Rounded minimum height
    surf_max: number;     // Rounded maximum height
    surf_human: string;   // "Chest to overhead"
    surf_raw_min: number; // Exact minimum height
    surf_raw_max: number; // Exact maximum height
    power: number;        // Wave energy
    optimal_score: number;
  };

  wind?: {
    speed: number;
    gust: number;
    direction: number;      // Degrees 0-360
    direction_type: WindType;
    optimal_score: number;
  };

  weather?: {
    temperature: number;
    condition: string;      // Weather condition enum
    pressure: number;       // Millibars
  };

  swells?: SwellComponent[]; // Only if include=swells
}
```

### Swell Component Object

```typescript
interface SwellComponent {
  index: number;          // 0-5, position in original array
  active: boolean;        // true if height > 0
  height: number;         // Swell height
  period: number;         // Seconds
  direction: number;      // Degrees 0-360
  direction_min: number;  // Minimum direction spread
  impact: number;         // 0-1, contribution to total surf
  power: number;          // Swell energy
  optimal_score: number;
}
```

### Tide Event Object

```typescript
interface TideEvent {
  timestamp: string;
  type: "HIGH" | "LOW" | "NORMAL";
  height: number;         // Always in meters
}
```

### Sunlight Object

```typescript
interface Sunlight {
  date: string;           // ISO date
  dawn: string;           // ISO timestamp
  sunrise: string;        // ISO timestamp
  sunset: string;         // ISO timestamp
  dusk: string;           // ISO timestamp
}
```

### Enum Values

**RatingKey:**
```
FLAT, VERY_POOR, POOR, POOR_TO_FAIR, FAIR, FAIR_TO_GOOD, GOOD, GOOD_TO_EPIC, EPIC
```

**WindType:**
```
Offshore, Cross-offshore, Crosswind, Cross-onshore, Onshore
```

**WeatherCondition (examples):**
```
NIGHT_CLEAR, NIGHT_BRIEF_SHOWERS_POSSIBLE, DAWN_CLEAR, DAY_PARTLY_CLOUDY,
DAY_SUNNY, DAY_CLOUDY, DAY_RAIN, DUSK_CLEAR, etc.
```

---

## Unit Conversion

### Request Parameter

```
GET /spots/{id}/forecast?units=metric
GET /spots/{id}/forecast?units=imperial
```

### Conversion Table

| Field | Imperial (default) | Metric | Conversion |
|-------|-------------------|--------|------------|
| wave_height (surf_min, surf_max, surf_raw_*) | ft | m | ÷ 3.281 |
| swell_height | ft | m | ÷ 3.281 |
| wind_speed, gust | mph | km/h | × 1.609 |
| temperature | °F | °C | Stored as °C; (°C × 9/5) + 32 for °F |
| tide_height | m | m | No conversion |
| direction | degrees | degrees | No conversion |
| period | seconds | seconds | No conversion |
| pressure | millibars | millibars | No conversion |

### Response Includes Active Units

```json
{
  "metadata": {
    "units": {
      "system": "metric",
      "wave_height": "m",
      "wind_speed": "km/h",
      "temperature": "C",
      "tide_height": "m"
    }
  }
}
```

---

## Pagination and Caching

### Cursor-Based Pagination

List endpoints return pagination info:

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

To get the next page:

```
GET /spots?cursor=eyJvZmZzZXQiOjEwMH0=
```

### Page Size Limits

| Endpoint | Default | Maximum |
|----------|---------|---------|
| `/spots` | 100 | 1000 |
| `/spots/{id}/scrapes` | 100 | 500 |
| `/forecast/discover` | 20 | 100 |

### Caching Headers

Responses include caching headers:

```http
ETag: "scrape-2026-01-17T14:43:39Z"
Cache-Control: max-age=1800
Last-Modified: Sat, 17 Jan 2026 14:43:39 GMT
```

### Cache Durations

| Data Type | Cache Duration | Rationale |
|-----------|----------------|-----------|
| Current forecast | 30 minutes | Scrapes happen ~every 6 hours |
| Spot metadata | 24 hours | Rarely changes |
| Historical data | 1 year | Immutable |
| Accuracy analysis | 24 hours | Computed aggregates |

### Conditional Requests

Clients can use ETags for efficient polling:

```http
GET /spots/584204204e65fad6a77090d2/forecast
If-None-Match: "scrape-2026-01-17T14:43:39Z"
```

Returns `304 Not Modified` if forecast hasn't changed.

---

## Error Handling

### Error Response Format

```json
{
  "error": {
    "code": "SPOT_NOT_FOUND",
    "message": "Spot with ID 'abc123' not found",
    "details": {
      "spot_id": "abc123"
    }
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
| `UNAUTHORIZED` | 401 | Missing or invalid API key |
| `FORBIDDEN` | 403 | API key lacks required permissions |
| `INTERNAL_ERROR` | 500 | Server error |

### Example Error Responses

**Invalid spot:**
```json
{
  "error": {
    "code": "SPOT_NOT_FOUND",
    "message": "Spot with ID 'invalid-id' not found",
    "details": {
      "spot_id": "invalid-id"
    }
  }
}
```

**Invalid date range:**
```json
{
  "error": {
    "code": "INVALID_DATE_RANGE",
    "message": "Date range exceeds maximum of 365 days",
    "details": {
      "from": "2025-01-01",
      "to": "2026-06-01",
      "max_days": 365
    }
  }
}
```

**Rate limited:**
```json
{
  "error": {
    "code": "RATE_LIMITED",
    "message": "Rate limit exceeded. Try again in 45 seconds.",
    "details": {
      "retry_after": 45,
      "limit": 1000,
      "window": "hour"
    }
  }
}
```

---

## Authentication and Rate Limiting

### Phase 1: Internal API

Simple API key authentication for internal use:

```http
GET /spots/584204204e65fad6a77090d2/forecast
X-API-Key: your-api-key-here
```

- API keys issued manually
- No rate limiting
- Internal documentation only

### Phase 2: Public API

Full API key management with rate limiting:

```http
GET /spots/584204204e65fad6a77090d2/forecast
Authorization: Bearer your-api-key-here
```

#### Rate Limits

| Tier | Requests/Hour | Requests/Day | History Access |
|------|---------------|--------------|----------------|
| Free | 100 | 1,000 | 7 days |
| Basic | 1,000 | 10,000 | 30 days |
| Pro | 10,000 | 100,000 | Full |
| Enterprise | Custom | Custom | Full |

#### Rate Limit Headers

```http
X-RateLimit-Limit: 1000
X-RateLimit-Remaining: 847
X-RateLimit-Reset: 1737142800
```

---

## Database Architecture

### Hybrid Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                         API Layer                                │
│                    (FastAPI + Lambda)                           │
└───────────────────┬─────────────────────┬───────────────────────┘
                    │                     │
                    ▼                     ▼
    ┌───────────────────────┐   ┌───────────────────────┐
    │    Current Forecast   │   │   Historical Data     │
    │    (PostgreSQL /      │   │   (Parquet on S3 +    │
    │     Aurora Serverless)│   │    DuckDB / Athena)   │
    └───────────┬───────────┘   └───────────┬───────────┘
                │                           │
                └─────────────┬─────────────┘
                              │
                    ┌─────────┴─────────┐
                    │     ETL Job       │
                    │  (Scrape → Both)  │
                    └─────────┬─────────┘
                              │
                    ┌─────────┴─────────┐
                    │   Raw JSON (S3)   │
                    │   from Scrapers   │
                    └───────────────────┘
```

### Current Forecast Layer (PostgreSQL)

For low-latency current forecast queries:

**Why PostgreSQL over DynamoDB:**
- Natural joins between forecast types (wave + wind + rating)
- SQL functions for unit conversion and aggregations
- Better fit for computed endpoints (best windows, daily summary)
- Easier development and debugging
- Aurora Serverless for cost-effective scaling

**Schema approach:**
- Materialized view of "current" forecast (latest scrape only)
- Refresh on each new scrape
- Index on `(spot_id, forecast_ts)`
- TTL cleanup for old data

### Historical Data Layer (Parquet + DuckDB)

For analytical queries and historical access:

**Why Parquet on S3:**
- Cost-effective storage (~$0.023/GB/month)
- Columnar format optimized for analytical queries
- Works with DuckDB (fast, in-process), Athena (serverless), pandas
- Immutable data - perfect for long-term caching

**Partitioning strategy:**
```
s3://surf-alerts-data/forecasts/
  fact_rating/
    year=2026/
      month=01/
        spot_id=584204204e65fad6a77090d2/
          data_20260117.parquet
```

### Caching Layer

For sub-10ms response times on popular spots:

- **CloudFront** - Edge caching for static responses
- **ElastiCache (Redis)** - Computed aggregates (daily summaries, best windows)

---

## Implementation Recommendations

### Technology Stack

| Layer | Technology | Rationale |
|-------|------------|-----------|
| API Framework | FastAPI (Python) | Async, auto OpenAPI docs, Pydantic validation |
| Hosting | Lambda + API Gateway | Serverless, scales to zero, pay-per-request |
| Current DB | Aurora Serverless v2 | PostgreSQL compatibility, auto-scaling |
| Historical DB | Parquet + DuckDB | Cost-effective, analytical queries |
| Cache | CloudFront + ElastiCache | Edge caching + computed aggregates |
| Auth | API Gateway API keys | Simple, built-in rate limiting |

### ETL Pipeline

```
Scraper Lambda
    │
    ▼
Raw JSON (S3)
    │
    ├──▶ PostgreSQL (current forecast, last scrape only)
    │      - Upsert by (spot_id, forecast_ts)
    │      - Delete forecasts older than 7 days
    │
    └──▶ Parquet (historical archive)
           - Append to partitioned files
           - Partitioned by year/month/spot_id
```

### API Project Structure

```
packages/api/
├── src/
│   └── forecast_api/
│       ├── __init__.py
│       ├── main.py              # FastAPI app entry point
│       ├── config.py            # Settings and configuration
│       ├── dependencies.py      # Dependency injection
│       ├── routers/
│       │   ├── spots.py         # /spots endpoints
│       │   ├── forecast.py      # /spots/{id}/forecast endpoints
│       │   ├── history.py       # /spots/{id}/history endpoints
│       │   └── discovery.py     # /forecast/compare, /forecast/discover
│       ├── services/
│       │   ├── forecast.py      # Forecast business logic
│       │   ├── history.py       # Historical queries
│       │   ├── accuracy.py      # Accuracy calculations
│       │   └── discovery.py     # Regional search logic
│       ├── repositories/
│       │   ├── postgres.py      # PostgreSQL queries
│       │   └── parquet.py       # Parquet/DuckDB queries
│       ├── models/
│       │   ├── spot.py          # Pydantic models for spots
│       │   ├── forecast.py      # Pydantic models for forecasts
│       │   └── errors.py        # Error response models
│       └── utils/
│           ├── units.py         # Unit conversion functions
│           └── pagination.py    # Cursor pagination helpers
├── tests/
│   ├── unit/
│   ├── integration/
│   └── e2e/
├── pyproject.toml
└── Dockerfile
```

---

## Verification Plan

When implemented, verify with these tests:

### 1. Current Forecast Accuracy

Compare `/spots/{id}/forecast` response against raw scraped JSON:

```python
def test_forecast_matches_raw_json():
    # Fetch API response
    response = client.get(f"/spots/{SPOT_ID}/forecast")
    api_data = response.json()

    # Load raw JSON from S3
    raw_data = load_raw_json(SPOT_ID, api_data["metadata"]["scrape_ts"])

    # Compare wave data
    assert api_data["hourly"][0]["wave"]["surf_min"] == raw_data["wave"]["data"]["wave"][0]["surf"]["min"]
```

### 2. Unit Conversion

Request same endpoint with `?units=metric` and `?units=imperial`:

```python
def test_unit_conversion():
    imperial = client.get(f"/spots/{SPOT_ID}/forecast?units=imperial").json()
    metric = client.get(f"/spots/{SPOT_ID}/forecast?units=metric").json()

    # Wave height should convert ft → m
    assert abs(imperial["hourly"][0]["wave"]["surf_min"] / 3.281 -
               metric["hourly"][0]["wave"]["surf_min"]) < 0.01

    # Wind speed should convert mph → km/h
    assert abs(imperial["hourly"][0]["wind"]["speed"] * 1.609 -
               metric["hourly"][0]["wind"]["speed"]) < 0.1
```

### 3. Historical Retrieval

Request `/spots/{id}/history?from=...&to=...` and verify data matches Parquet:

```python
def test_historical_retrieval():
    response = client.get(f"/spots/{SPOT_ID}/history?from=2026-01-01&to=2026-01-07")
    api_data = response.json()

    # Query Parquet directly
    parquet_data = query_parquet(SPOT_ID, "2026-01-01", "2026-01-07")

    # Compare daily aggregates
    for day in api_data["data"]:
        parquet_day = find_day(parquet_data, day["date"])
        assert abs(day["rating_avg"] - parquet_day["rating_avg"]) < 0.01
```

### 4. Best Windows Logic

Manually verify that returned windows meet all filter criteria:

```python
def test_best_windows_criteria():
    response = client.get(
        f"/spots/{SPOT_ID}/forecast/best?"
        "min_surf=3&max_wind=15&wind_type=offshore&min_rating=3"
    )
    windows = response.json()["windows"]

    for window in windows:
        # Every hour in window should meet criteria
        hourly = get_hourly_for_window(SPOT_ID, window["start"], window["end"])
        for hour in hourly:
            assert hour["wave"]["surf_min"] >= 3
            assert hour["wind"]["speed"] <= 15
            assert hour["wind"]["direction_type"] == "Offshore"
            assert hour["rating"]["value"] >= 3
```

### 5. Multi-Spot Compare

Ensure rankings are consistent with individual spot forecasts:

```python
def test_multi_spot_ranking():
    spots = ["spot1", "spot2", "spot3"]
    timestamp = "2026-01-17T10:00:00Z"

    # Get comparison
    compare = client.get(f"/forecast/compare?spots={','.join(spots)}&timestamp={timestamp}")

    # Get individual forecasts
    individual_ratings = {}
    for spot_id in spots:
        forecast = client.get(f"/spots/{spot_id}/forecast?start={timestamp}&hours=1")
        individual_ratings[spot_id] = forecast.json()["hourly"][0]["rating"]["value"]

    # Rankings should match individual ratings
    ranked = sorted(individual_ratings.items(), key=lambda x: x[1], reverse=True)
    for i, spot in enumerate(compare.json()["spots"]):
        assert spot["spot"]["id"] == ranked[i][0]
        assert spot["rank"] == i + 1
```

### 6. Caching Behavior

Verify ETag headers change only when new scrape arrives:

```python
def test_etag_caching():
    # First request
    r1 = client.get(f"/spots/{SPOT_ID}/forecast")
    etag1 = r1.headers["ETag"]

    # Second request (no new scrape)
    r2 = client.get(f"/spots/{SPOT_ID}/forecast", headers={"If-None-Match": etag1})
    assert r2.status_code == 304

    # Trigger new scrape
    trigger_scrape(SPOT_ID)

    # Third request (after new scrape)
    r3 = client.get(f"/spots/{SPOT_ID}/forecast", headers={"If-None-Match": etag1})
    assert r3.status_code == 200
    assert r3.headers["ETag"] != etag1
```

---

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

## OpenAPI Specification

When implemented, the API will provide an OpenAPI 3.0 specification at:

```
GET /openapi.json
GET /docs          # Swagger UI
GET /redoc         # ReDoc
```

This enables:
- Auto-generated client SDKs
- Interactive API documentation
- Request/response validation
- Type-safe integrations
