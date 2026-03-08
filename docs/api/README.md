# API Design

> **Status: PLANNED** | Not yet implemented

Design spec for the Surf Forecast API, which will serve both current forecasts and historical data from the normalized Parquet data model.

## Purpose

The Surf Forecast API provides programmatic access to surf condition data, enabling:

- **Single-spot forecasts** — Detailed hourly predictions for a specific beach
- **Multi-spot discovery** — Find the best conditions across a region
- **Session planning** — Identify optimal surf windows based on criteria
- **Forecast accuracy analysis** — Compare predictions against actual conditions

## Use Cases

| Consumer | Primary Endpoints | Use Case |
|----------|-------------------|----------|
| Mobile app | `/spots/{id}/forecast` | Display current conditions |
| Trip planner | `/forecast/discover` | Find best spots for upcoming weekend |
| Data analyst | `/spots/{id}/history`, `/spots/{id}/accuracy` | Forecast model evaluation |
| Alert system | `/spots/{id}/forecast/best` | Notify when conditions match preferences |

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

## Data Shape Philosophy

### The "Session" Concept

Surfers think in **sessions** — a window of time when conditions align. The API supports both:

1. **Raw time-series** — Hourly data points per forecast type
2. **Session views** — Aggregated windows with combined conditions

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

## Unit Conversion

### Request Parameter

```
GET /spots/{id}/forecast?units=metric
GET /spots/{id}/forecast?units=imperial
```

### Conversion Table

| Field | Imperial (default) | Metric | Conversion |
|-------|-------------------|--------|------------|
| wave_height (surf_min, surf_max, surf_raw_*) | ft | m | / 3.281 |
| swell_height | ft | m | / 3.281 |
| wind_speed, gust | mph | km/h | x 1.609 |
| temperature | F | C | Stored as C; (C x 9/5) + 32 for F |
| tide_height | ft | m | / 3.281 |
| direction | degrees | degrees | No conversion |
| period | seconds | seconds | No conversion |
| pressure | millibars | millibars | No conversion |

## Documentation

| Page | Contents |
|------|----------|
| [Endpoints](endpoints.md) | All 10 endpoint specs with request/response examples |
| [Implementation Guide](implementation-guide.md) | DB architecture, tech stack, ETL pipeline, project structure |
