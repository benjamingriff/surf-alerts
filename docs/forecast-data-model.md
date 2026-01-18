# Forecast Data Model

This document describes how raw surf forecast JSON data is transformed into a queryable table format (Parquet). It covers the original data structure, the target schema, transformation mappings, and example queries.

---

## Table of Contents

1. [Overview](#overview)
2. [Original Data Structure](#original-data-structure)
3. [Target Schema Design](#target-schema-design)
4. [Field Mappings](#field-mappings)
5. [Handling Nested Structures](#handling-nested-structures)
6. [Partitioning Strategy](#partitioning-strategy)
7. [Example Queries](#example-queries)
8. [Reconstructing Original Data](#reconstructing-original-data)
9. [Design Justifications](#design-justifications)
10. [Storage Estimates](#storage-estimates)

---

## Overview

### Problem Statement

The forecast scraper produces deeply nested JSON files from 6 Surfline API endpoints. These files are excellent for storage but difficult to query efficiently. We need to:

1. Flatten nested structures into queryable columns
2. Handle arrays (especially the `swells[]` array with 6 elements per wave entry)
3. Support time-series queries across forecast types
4. Enable joins between different forecast types (wave + wind + rating)
5. Keep storage efficient with columnar compression

### Solution Summary

**Approach:** Hybrid star schema with Parquet storage

| Component | Choice | Rationale |
|-----------|--------|-----------|
| Storage Format | Parquet on S3 | Columnar compression, works with DuckDB/Athena/pandas |
| Schema Style | Star schema (7 fact tables) | Different cardinalities per forecast type (16-384 rows) |
| Swells Handling | Separate `fact_swells` table | Enables flexible swell queries without 42 sparse columns |
| Partitioning | `year/month/spot_id` | Optimizes time-range + spot filtering |

---

## Original Data Structure

Each scrape produces two files per spot:

### metadata.json

```json
{
  "spot_id": "584204204e65fad6a77090d2",
  "timestamp": "2026-01-17T14:43:39.398066",
  "scraper": "forecast"
}
```

### data.json

Contains 6 top-level forecast types: `rating`, `sunlight`, `tides`, `wave`, `weather`, `wind`.

Each forecast type has this structure:

```json
{
  "associated": { /* metadata: location, units, timestamps */ },
  "data": { /* array(s) of forecast values */ },
  "permissions": { /* API permission info */ }
}
```

---

### Rating (120 rows per scrape, hourly for 5 days)

```json
{
  "rating": {
    "associated": {
      "location": {
        "lon": -3.728,
        "lat": 51.488
      },
      "runInitializationTimestamp": 1768608000
    },
    "data": {
      "rating": [
        {
          "timestamp": 1768608000,
          "utcOffset": 0,
          "rating": {
            "key": "FAIR",
            "value": 3
          }
        },
        {
          "timestamp": 1768611600,
          "utcOffset": 0,
          "rating": {
            "key": "FAIR_TO_GOOD",
            "value": 4
          }
        }
        // ... 118 more entries (hourly)
      ]
    },
    "permissions": { /* ... */ }
  }
}
```

**Key observations:**
- `rating` is nested: `data.rating[].rating.key` and `data.rating[].rating.value`
- Timestamps are Unix epoch (seconds)
- 120 entries = 5 days * 24 hours

---

### Sunlight (16 rows per scrape, daily for 16 days)

```json
{
  "sunlight": {
    "associated": {
      "location": {
        "lon": -3.728,
        "lat": 51.488
      }
    },
    "data": {
      "sunlight": [
        {
          "midnight": 1768608000,
          "midnightUTCOffset": 0,
          "dawn": 1768635308,
          "dawnUTCOffset": 0,
          "sunrise": 1768637604,
          "sunriseUTCOffset": 0,
          "sunset": 1768667918,
          "sunsetUTCOffset": 0,
          "dusk": 1768670214,
          "duskUTCOffset": 0
        }
        // ... 15 more entries (daily)
      ]
    }
  }
}
```

**Key observations:**
- No `timestamp` field - uses `midnight` as the anchor
- Each day has 5 time markers: midnight, dawn, sunrise, sunset, dusk
- Each marker has its own UTC offset (for DST handling)

---

### Tides (168 rows per scrape, irregular intervals over 6 days)

```json
{
  "tides": {
    "associated": {
      "utcOffset": 0,
      "units": {
        "tideHeight": "M"
      },
      "tideLocation": {
        "name": "Port Talbot",
        "min": -0.19,
        "max": 11.07,
        "lon": -3.783,
        "lat": 51.6,
        "mean": 0
      }
    },
    "data": {
      "tides": [
        {
          "timestamp": 1768608000,
          "utcOffset": 0,
          "type": "NORMAL",
          "height": 2.98
        },
        {
          "timestamp": 1768627462,
          "utcOffset": 0,
          "type": "HIGH",
          "height": 8.52
        },
        {
          "timestamp": 1768649435,
          "utcOffset": 0,
          "type": "LOW",
          "height": 2.58
        }
        // ... more entries
      ]
    }
  }
}
```

**Key observations:**
- `tideLocation` is DIFFERENT from the spot location (references a tide station)
- `type` indicates tide state: "NORMAL", "HIGH", "LOW"
- Irregular timestamps (HIGH/LOW events inserted between hourly NORMAL readings)
- Height in meters (unit specified in `associated.units`)

---

### Wave (120 rows per scrape, hourly for 5 days) - MOST COMPLEX

```json
{
  "wave": {
    "associated": {
      "units": {
        "swellHeight": "FT",
        "waveHeight": "FT"
      },
      "utcOffset": 0,
      "location": {
        "lon": -3.728,
        "lat": 51.488
      },
      "forecastLocation": {
        "lon": -3.739,
        "lat": 51.473
      },
      "offshoreLocation": {
        "lon": -3.8,
        "lat": 51.4
      },
      "runInitializationTimestamp": 1768608000
    },
    "data": {
      "wave": [
        {
          "timestamp": 1768608000,
          "probability": 100,
          "utcOffset": 0,
          "surf": {
            "min": 4,
            "max": 6,
            "plus": false,
            "humanRelation": "Chest to overhead",
            "raw": {
              "min": 4.68504,
              "max": 5.57743
            },
            "optimalScore": 2
          },
          "power": 249.55623,
          "swells": [
            {
              "height": 0,
              "period": 0,
              "impact": 0,
              "power": 0,
              "direction": 0,
              "directionMin": 0,
              "optimalScore": 0
            },
            {
              "height": 3.44898,
              "period": 10,
              "impact": 0.4868,
              "power": 96.69214,
              "direction": 248.57898,
              "directionMin": 236.665615,
              "optimalScore": 1
            },
            {
              "height": 2.78517,
              "period": 15,
              "impact": 0.5132,
              "power": 152.86409,
              "direction": 248.66003,
              "directionMin": 244.237095,
              "optimalScore": 1
            },
            {
              "height": 0,
              "period": 0,
              "impact": 0,
              "power": 0,
              "direction": 0,
              "directionMin": 0,
              "optimalScore": 0
            },
            {
              "height": 0,
              "period": 0,
              "impact": 0,
              "power": 0,
              "direction": 0,
              "directionMin": 0,
              "optimalScore": 0
            },
            {
              "height": 0,
              "period": 0,
              "impact": 0,
              "power": 0,
              "direction": 0,
              "directionMin": 0,
              "optimalScore": 0
            }
          ]
        }
        // ... 119 more entries
      ]
    }
  }
}
```

**Key observations:**
- **Deepest nesting**: `surf.raw.min`, `surf.raw.max`
- **Three location references**: `location`, `forecastLocation`, `offshoreLocation`
- **swells array**: Always 6 elements, many with height=0 (inactive swells)
- Each swell has 7 fields: height, period, impact, power, direction, directionMin, optimalScore

---

### Weather (384 rows per scrape, hourly for 16 days)

```json
{
  "weather": {
    "associated": {
      "units": {
        "temperature": "C"
      },
      "utcOffset": 0,
      "weatherIconPath": "https://wa.cdn-surfline.com/quiver/3.0.0/weathericons",
      "runInitializationTimestamp": 1768608000
    },
    "data": {
      "sunlightTimes": [
        // Same structure as sunlight type (duplicated data)
      ],
      "weather": [
        {
          "timestamp": 1768608000,
          "utcOffset": 0,
          "temperature": 6.37795,
          "condition": "NIGHT_BRIEF_SHOWERS_POSSIBLE",
          "pressure": 1007
        },
        {
          "timestamp": 1768611600,
          "utcOffset": 0,
          "temperature": 6.3324,
          "condition": "NIGHT_CLEAR",
          "pressure": 1007
        }
        // ... 382 more entries
      ]
    }
  }
}
```

**Key observations:**
- **Two data arrays**: `sunlightTimes` (same as sunlight type) + `weather`
- 384 entries (16 days * 24 hours)
- Temperature in Celsius, pressure in millibars
- `condition` is a string enum (NIGHT_CLEAR, NIGHT_BRIEF_SHOWERS_POSSIBLE, etc.)

---

### Wind (120 rows per scrape, hourly for 5 days)

```json
{
  "wind": {
    "associated": {
      "units": {
        "windSpeed": "MPH"
      },
      "utcOffset": 0,
      "location": {
        "lon": -3.728,
        "lat": 51.488
      },
      "runInitializationTimestamp": 1768608000,
      "windStation": null,
      "lastObserved": null
    },
    "data": {
      "wind": [
        {
          "timestamp": 1768608000,
          "utcOffset": 0,
          "speed": 9.27147,
          "direction": 129.78214,
          "directionType": "Offshore",
          "gust": 13.21784,
          "optimalScore": 0
        }
        // ... 119 more entries
      ]
    }
  }
}
```

**Key observations:**
- `directionType` is a string enum: "Offshore", "Onshore", "Crosswind"
- `optimalScore` indicates how favorable the wind is for surfing
- Nullable fields: `windStation`, `lastObserved` (for observed vs forecast data)

---

## Target Schema Design

### Schema Diagram

```
                              ┌─────────────────┐
                              │   dim_spots     │
                              │─────────────────│
                              │ spot_id (PK)    │
                              │ name            │
                              │ lat, lng        │
                              │ timezone        │
                              └────────┬────────┘
                                       │
       ┌───────────────────────────────┼───────────────────────────────┐
       │               │               │               │               │
       ▼               ▼               ▼               ▼               ▼
┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐
│ fact_rating │ │  fact_wave  │ │  fact_wind  │ │fact_weather │ │ fact_tides  │
│─────────────│ │─────────────│ │─────────────│ │─────────────│ │─────────────│
│ spot_id     │ │ spot_id     │ │ spot_id     │ │ spot_id     │ │ spot_id     │
│ forecast_ts │ │ forecast_ts │ │ forecast_ts │ │ forecast_ts │ │ forecast_ts │
│ scrape_ts   │ │ scrape_ts   │ │ scrape_ts   │ │ scrape_ts   │ │ scrape_ts   │
│ rating_key  │ │ surf_min    │ │ speed       │ │ temperature │ │ tide_type   │
│ rating_value│ │ surf_max    │ │ gust        │ │ condition   │ │ height      │
│ ...         │ │ power       │ │ direction   │ │ pressure    │ │ ...         │
└─────────────┘ │ ...         │ │ ...         │ └─────────────┘ └─────────────┘
                └──────┬──────┘ └─────────────┘
                       │
                       ▼
                ┌─────────────┐
                │ fact_swells │
                │─────────────│
                │ spot_id     │
                │ forecast_ts │
                │ scrape_ts   │
                │ swell_index │ ◄── 0-5 (position in original array)
                │ height      │
                │ period      │
                │ impact      │
                │ ...         │
                └─────────────┘

                ┌─────────────┐
                │dim_sunlight │
                │─────────────│
                │ spot_id     │
                │ date        │
                │ scrape_ts   │
                │ dawn        │
                │ sunrise     │
                │ sunset      │
                │ dusk        │
                └─────────────┘
```

---

### Table Definitions

#### fact_rating

| Column | Type | Source Path | Notes |
|--------|------|-------------|-------|
| spot_id | STRING | metadata.spot_id | Primary key component |
| forecast_ts | TIMESTAMP | rating.data.rating[].timestamp | Converted from Unix epoch |
| scrape_ts | TIMESTAMP | metadata.timestamp | When the forecast was scraped |
| rating_key | STRING | rating.data.rating[].rating.key | "FAIR", "GOOD", "FAIR_TO_GOOD" |
| rating_value | INT32 | rating.data.rating[].rating.value | 1-5 |
| utc_offset | INT32 | rating.data.rating[].utcOffset | Hours from UTC |
| location_lon | FLOAT64 | rating.associated.location.lon | Spot longitude |
| location_lat | FLOAT64 | rating.associated.location.lat | Spot latitude |
| run_init_ts | TIMESTAMP | rating.associated.runInitializationTimestamp | Model run time |

**Row count per scrape:** 120 (hourly for 5 days)

---

#### fact_wave

| Column | Type | Source Path | Notes |
|--------|------|-------------|-------|
| spot_id | STRING | metadata.spot_id | |
| forecast_ts | TIMESTAMP | wave.data.wave[].timestamp | |
| scrape_ts | TIMESTAMP | metadata.timestamp | |
| surf_min | INT32 | wave.data.wave[].surf.min | Feet (integer) |
| surf_max | INT32 | wave.data.wave[].surf.max | Feet (integer) |
| surf_plus | BOOLEAN | wave.data.wave[].surf.plus | Indicates "+" condition |
| surf_human_relation | STRING | wave.data.wave[].surf.humanRelation | "Chest to overhead" |
| surf_raw_min | FLOAT64 | wave.data.wave[].surf.raw.min | Exact value in feet |
| surf_raw_max | FLOAT64 | wave.data.wave[].surf.raw.max | Exact value in feet |
| surf_optimal_score | INT32 | wave.data.wave[].surf.optimalScore | |
| power | FLOAT64 | wave.data.wave[].power | Wave energy |
| probability | INT32 | wave.data.wave[].probability | 0-100 |
| utc_offset | INT32 | wave.data.wave[].utcOffset | |
| location_lon | FLOAT64 | wave.associated.location.lon | Spot location |
| location_lat | FLOAT64 | wave.associated.location.lat | |
| forecast_location_lon | FLOAT64 | wave.associated.forecastLocation.lon | Model grid point |
| forecast_location_lat | FLOAT64 | wave.associated.forecastLocation.lat | |
| offshore_location_lon | FLOAT64 | wave.associated.offshoreLocation.lon | Offshore reference |
| offshore_location_lat | FLOAT64 | wave.associated.offshoreLocation.lat | |
| run_init_ts | TIMESTAMP | wave.associated.runInitializationTimestamp | |

**Row count per scrape:** 120 (hourly for 5 days)

---

#### fact_swells (normalized from wave)

| Column | Type | Source Path | Notes |
|--------|------|-------------|-------|
| spot_id | STRING | metadata.spot_id | |
| forecast_ts | TIMESTAMP | wave.data.wave[].timestamp | Links to fact_wave |
| scrape_ts | TIMESTAMP | metadata.timestamp | |
| swell_index | INT32 | Array position (0-5) | Preserves original order |
| height | FLOAT64 | wave.data.wave[].swells[i].height | Feet |
| period | INT32 | wave.data.wave[].swells[i].period | Seconds |
| impact | FLOAT64 | wave.data.wave[].swells[i].impact | 0-1 contribution |
| power | FLOAT64 | wave.data.wave[].swells[i].power | |
| direction | FLOAT64 | wave.data.wave[].swells[i].direction | Degrees (0-360) |
| direction_min | FLOAT64 | wave.data.wave[].swells[i].directionMin | |
| optimal_score | INT32 | wave.data.wave[].swells[i].optimalScore | |

**Row count per scrape:** ~240 (after filtering zero-height swells)
- Original: 120 wave entries * 6 swells = 720 rows
- Many swells have height=0 (inactive), filtered during ETL

---

#### fact_wind

| Column | Type | Source Path | Notes |
|--------|------|-------------|-------|
| spot_id | STRING | metadata.spot_id | |
| forecast_ts | TIMESTAMP | wind.data.wind[].timestamp | |
| scrape_ts | TIMESTAMP | metadata.timestamp | |
| speed | FLOAT64 | wind.data.wind[].speed | MPH |
| gust | FLOAT64 | wind.data.wind[].gust | MPH |
| direction | FLOAT64 | wind.data.wind[].direction | Degrees (0-360) |
| direction_type | STRING | wind.data.wind[].directionType | "Offshore", "Onshore", "Crosswind" |
| optimal_score | INT32 | wind.data.wind[].optimalScore | |
| utc_offset | INT32 | wind.data.wind[].utcOffset | |
| location_lon | FLOAT64 | wind.associated.location.lon | |
| location_lat | FLOAT64 | wind.associated.location.lat | |
| run_init_ts | TIMESTAMP | wind.associated.runInitializationTimestamp | |

**Row count per scrape:** 120

---

#### fact_weather

| Column | Type | Source Path | Notes |
|--------|------|-------------|-------|
| spot_id | STRING | metadata.spot_id | |
| forecast_ts | TIMESTAMP | weather.data.weather[].timestamp | |
| scrape_ts | TIMESTAMP | metadata.timestamp | |
| temperature | FLOAT64 | weather.data.weather[].temperature | Celsius |
| condition | STRING | weather.data.weather[].condition | Enum string |
| pressure | INT32 | weather.data.weather[].pressure | Millibars |
| utc_offset | INT32 | weather.data.weather[].utcOffset | |
| run_init_ts | TIMESTAMP | weather.associated.runInitializationTimestamp | |

**Row count per scrape:** 384 (hourly for 16 days)

---

#### fact_tides

| Column | Type | Source Path | Notes |
|--------|------|-------------|-------|
| spot_id | STRING | metadata.spot_id | |
| forecast_ts | TIMESTAMP | tides.data.tides[].timestamp | May be non-hourly |
| scrape_ts | TIMESTAMP | metadata.timestamp | |
| tide_type | STRING | tides.data.tides[].type | "NORMAL", "HIGH", "LOW" |
| height | FLOAT64 | tides.data.tides[].height | Meters |
| utc_offset | INT32 | tides.data.tides[].utcOffset | |
| tide_location_name | STRING | tides.associated.tideLocation.name | Tide station name |
| tide_location_lon | FLOAT64 | tides.associated.tideLocation.lon | Different from spot! |
| tide_location_lat | FLOAT64 | tides.associated.tideLocation.lat | |
| tide_location_min | FLOAT64 | tides.associated.tideLocation.min | Min possible height |
| tide_location_max | FLOAT64 | tides.associated.tideLocation.max | Max possible height |
| tide_location_mean | FLOAT64 | tides.associated.tideLocation.mean | |

**Row count per scrape:** 168 (irregular intervals, includes HIGH/LOW events)

---

#### dim_sunlight

| Column | Type | Source Path | Notes |
|--------|------|-------------|-------|
| spot_id | STRING | metadata.spot_id | |
| date | DATE | Derived from midnight | YYYY-MM-DD |
| scrape_ts | TIMESTAMP | metadata.timestamp | |
| midnight | TIMESTAMP | sunlight.data.sunlight[].midnight | |
| midnight_utc_offset | INT32 | sunlight.data.sunlight[].midnightUTCOffset | |
| dawn | TIMESTAMP | sunlight.data.sunlight[].dawn | |
| dawn_utc_offset | INT32 | sunlight.data.sunlight[].dawnUTCOffset | |
| sunrise | TIMESTAMP | sunlight.data.sunlight[].sunrise | |
| sunrise_utc_offset | INT32 | sunlight.data.sunlight[].sunriseUTCOffset | |
| sunset | TIMESTAMP | sunlight.data.sunlight[].sunset | |
| sunset_utc_offset | INT32 | sunlight.data.sunlight[].sunsetUTCOffset | |
| dusk | TIMESTAMP | sunlight.data.sunlight[].dusk | |
| dusk_utc_offset | INT32 | sunlight.data.sunlight[].duskUTCOffset | |

**Row count per scrape:** 16 (daily for 16 days)

---

## Field Mappings

### Nested Key to Column Mappings

| Original JSON Path | Target Column | Table |
|--------------------|---------------|-------|
| `rating.data.rating[].rating.key` | rating_key | fact_rating |
| `rating.data.rating[].rating.value` | rating_value | fact_rating |
| `wave.data.wave[].surf.min` | surf_min | fact_wave |
| `wave.data.wave[].surf.max` | surf_max | fact_wave |
| `wave.data.wave[].surf.plus` | surf_plus | fact_wave |
| `wave.data.wave[].surf.humanRelation` | surf_human_relation | fact_wave |
| `wave.data.wave[].surf.raw.min` | surf_raw_min | fact_wave |
| `wave.data.wave[].surf.raw.max` | surf_raw_max | fact_wave |
| `wave.data.wave[].surf.optimalScore` | surf_optimal_score | fact_wave |
| `wave.data.wave[].swells[i].height` | height | fact_swells |
| `wave.data.wave[].swells[i].period` | period | fact_swells |
| `wave.data.wave[].swells[i].impact` | impact | fact_swells |
| `wave.associated.location.lon` | location_lon | fact_wave |
| `wave.associated.forecastLocation.lon` | forecast_location_lon | fact_wave |
| `tides.associated.tideLocation.name` | tide_location_name | fact_tides |
| `tides.associated.tideLocation.min` | tide_location_min | fact_tides |

### Metadata Field Mappings

| Source | Target | Applied To |
|--------|--------|------------|
| metadata.spot_id | spot_id | All tables |
| metadata.timestamp | scrape_ts | All tables |
| *.associated.runInitializationTimestamp | run_init_ts | rating, wave, wind, weather |
| Array position (0-5) | swell_index | fact_swells |
| Derived from midnight timestamp | date | dim_sunlight |

---

## Handling Nested Structures

### The Swells Challenge

Each wave entry contains a `swells[]` array with 6 elements:

```json
"swells": [
  { "height": 0, "period": 0, ... },      // index 0 - inactive
  { "height": 3.4, "period": 10, ... },   // index 1 - active
  { "height": 2.7, "period": 15, ... },   // index 2 - active
  { "height": 0, "period": 0, ... },      // index 3 - inactive
  { "height": 0, "period": 0, ... },      // index 4 - inactive
  { "height": 0, "period": 0, ... }       // index 5 - inactive
]
```

### Options Considered

| Approach | Implementation | Pros | Cons |
|----------|----------------|------|------|
| **Separate table** (chosen) | `fact_swells` with swell_index | Filterable, aggregatable | Requires join |
| Flattened columns | 42 columns (6 * 7 fields) | No join needed | Sparse, hard to query "any swell with X" |
| JSON column | `swells JSON` in fact_wave | Simple schema | No columnar benefits, full scan required |

### Why Separate Table?

1. **Query flexibility**: Easily answer "find spots with period > 12s"
2. **Storage efficiency**: Filter out zero-height swells (reduces ~720 to ~240 rows)
3. **Aggregations**: Natural `AVG(period) WHERE impact > 0.3`
4. **Schema simplicity**: 7 columns vs 42 sparse columns

### Preserving swell_index

The `swell_index` column (0-5) preserves the original array position. This may be semantically meaningful (e.g., swells ordered by impact or direction group).

---

## Partitioning Strategy

### Chosen Strategy: `year/month/spot_id`

```
s3://surf-alerts-data/forecasts/
  fact_rating/
    year=2026/
      month=01/
        spot_id=584204204e65fad6a77090d2/
          data_20260117.parquet
          data_20260118.parquet
```

### Rationale

| Query Pattern | Partition Pruning |
|---------------|-------------------|
| "Last week's forecasts for spot X" | Prunes by month + spot_id |
| "All spots on 2026-01-17" | Prunes by year/month |
| "Historical data for spot X" | Prunes by spot_id across all partitions |

### File Size Targets

- **Target:** 1-5 MB per Parquet file
- **Per scrape:** ~65 KB total (all tables combined)
- **Recommendation:** Aggregate multiple scrapes per file (daily or weekly)

---

## Example Queries

### 1. Basic Time-Series Query

Get wave conditions for a spot over a week:

```sql
SELECT
    forecast_ts,
    surf_min,
    surf_max,
    surf_human_relation,
    power
FROM fact_wave
WHERE spot_id = '584204204e65fad6a77090d2'
  AND forecast_ts BETWEEN '2026-01-10' AND '2026-01-17'
ORDER BY forecast_ts;
```

### 2. Cross-Forecast Join

Combine wave + wind + rating for the same timestamps:

```sql
SELECT
    w.forecast_ts,
    w.surf_min,
    w.surf_max,
    wind.speed AS wind_speed,
    wind.direction_type,
    r.rating_key,
    r.rating_value
FROM fact_wave w
JOIN fact_wind wind
    ON w.spot_id = wind.spot_id
    AND w.forecast_ts = wind.forecast_ts
    AND w.scrape_ts = wind.scrape_ts
JOIN fact_rating r
    ON w.spot_id = r.spot_id
    AND w.forecast_ts = r.forecast_ts
    AND w.scrape_ts = r.scrape_ts
WHERE w.spot_id = '584204204e65fad6a77090d2'
  AND w.forecast_ts >= '2026-01-17';
```

### 3. Swell Analysis

Find spots with long-period swells (the main benefit of the separate swells table):

```sql
SELECT
    sw.spot_id,
    AVG(sw.period) AS avg_period,
    MAX(sw.height) AS max_height,
    SUM(sw.impact) AS total_impact
FROM fact_swells sw
WHERE sw.forecast_ts >= CURRENT_DATE
  AND sw.period >= 12
  AND sw.impact > 0.2
GROUP BY sw.spot_id
HAVING AVG(sw.period) >= 14
ORDER BY avg_period DESC;
```

### 4. Daylight Filtering

Get wave conditions during daylight hours only:

```sql
SELECT
    w.forecast_ts,
    w.surf_min,
    w.surf_max
FROM fact_wave w
JOIN dim_sunlight sun
    ON w.spot_id = sun.spot_id
    AND DATE(w.forecast_ts) = sun.date
WHERE w.spot_id = '584204204e65fad6a77090d2'
  AND w.forecast_ts >= sun.sunrise
  AND w.forecast_ts <= sun.sunset
ORDER BY w.forecast_ts;
```

### 5. Rating Distribution Over Time

```sql
SELECT
    DATE_TRUNC('day', forecast_ts) AS date,
    rating_key,
    COUNT(*) AS hours
FROM fact_rating
WHERE spot_id = '584204204e65fad6a77090d2'
  AND forecast_ts >= CURRENT_DATE - INTERVAL '30 days'
GROUP BY 1, 2
ORDER BY 1, 3 DESC;
```

### 6. Best Conditions Finder

Find hours with good waves, offshore wind, and favorable rating:

```sql
SELECT
    w.forecast_ts,
    w.surf_min,
    w.surf_max,
    wind.speed,
    wind.direction_type,
    r.rating_key
FROM fact_wave w
JOIN fact_wind wind
    ON w.spot_id = wind.spot_id
    AND w.forecast_ts = wind.forecast_ts
    AND w.scrape_ts = wind.scrape_ts
JOIN fact_rating r
    ON w.spot_id = r.spot_id
    AND w.forecast_ts = r.forecast_ts
    AND w.scrape_ts = r.scrape_ts
WHERE w.spot_id = '584204204e65fad6a77090d2'
  AND w.surf_min >= 3
  AND wind.direction_type = 'Offshore'
  AND wind.speed < 15
  AND r.rating_value >= 4
ORDER BY w.forecast_ts;
```

---

## Reconstructing Original Data

### Rebuild Rating JSON Array

```sql
SELECT JSON_GROUP_ARRAY(
    JSON_OBJECT(
        'timestamp', CAST(EXTRACT(EPOCH FROM forecast_ts) AS INTEGER),
        'utcOffset', utc_offset,
        'rating', JSON_OBJECT(
            'key', rating_key,
            'value', rating_value
        )
    ) ORDER BY forecast_ts
) AS rating_array
FROM fact_rating
WHERE spot_id = '584204204e65fad6a77090d2'
  AND scrape_ts = '2026-01-17T14:43:39.398066';
```

### Rebuild Wave + Swells JSON

```sql
WITH swells_agg AS (
    SELECT
        spot_id,
        forecast_ts,
        scrape_ts,
        JSON_GROUP_ARRAY(
            JSON_OBJECT(
                'height', height,
                'period', period,
                'impact', impact,
                'power', power,
                'direction', direction,
                'directionMin', direction_min,
                'optimalScore', optimal_score
            ) ORDER BY swell_index
        ) AS swells_json
    FROM fact_swells
    GROUP BY spot_id, forecast_ts, scrape_ts
)
SELECT
    w.forecast_ts,
    JSON_OBJECT(
        'timestamp', CAST(EXTRACT(EPOCH FROM w.forecast_ts) AS INTEGER),
        'probability', w.probability,
        'utcOffset', w.utc_offset,
        'surf', JSON_OBJECT(
            'min', w.surf_min,
            'max', w.surf_max,
            'plus', w.surf_plus,
            'humanRelation', w.surf_human_relation,
            'raw', JSON_OBJECT(
                'min', w.surf_raw_min,
                'max', w.surf_raw_max
            ),
            'optimalScore', w.surf_optimal_score
        ),
        'power', w.power,
        'swells', sw.swells_json
    ) AS wave_entry
FROM fact_wave w
LEFT JOIN swells_agg sw
    ON w.spot_id = sw.spot_id
    AND w.forecast_ts = sw.forecast_ts
    AND w.scrape_ts = sw.scrape_ts
WHERE w.spot_id = '584204204e65fad6a77090d2'
  AND w.scrape_ts = '2026-01-17T14:43:39.398066'
ORDER BY w.forecast_ts;
```

### Rebuild Full data.json Structure

To fully reconstruct the original JSON, you would:

1. Query each fact table for the same `spot_id` and `scrape_ts`
2. Aggregate into the nested structure
3. Re-add `associated` metadata (stored once per scrape, could be in a metadata table)

For full fidelity, consider storing the `associated` objects in a separate `fact_scrape_metadata` table:

```sql
CREATE TABLE fact_scrape_metadata (
    spot_id STRING,
    scrape_ts TIMESTAMP,
    forecast_type STRING,  -- 'rating', 'wave', etc.
    associated JSON        -- Original associated object
);
```

---

## Design Justifications

### Why Star Schema Over Wide Table?

| Consideration | Star Schema | Wide Table |
|---------------|-------------|------------|
| **Row counts** | Vary naturally (120-384) | Would require NULL padding or duplication |
| **NULL values** | Minimal | 30%+ (misaligned timestamps) |
| **Swell columns** | 7 per row | 42 sparse columns |
| **Query flexibility** | Independent queries per type | Must scan all columns |
| **Schema evolution** | Add new fact table | Migrate entire table |
| **Storage** | Efficient | Bloated with NULLs |

### Why Parquet Over Database?

| Factor | Parquet on S3 | Database (DynamoDB/RDS) |
|--------|---------------|-------------------------|
| **Cost** | ~$0.023/GB/month (S3) | Higher (provisioned or per-request) |
| **Query tools** | DuckDB, Athena, pandas | Requires connections, drivers |
| **Infrastructure** | Already using S3 | New resources needed |
| **Batch analytics** | Excellent (columnar) | Moderate |
| **Real-time** | Good (DuckDB in Lambda) | Excellent |
| **Schema changes** | Easy (additive) | Migrations required |

### Why Separate Swells Table?

The swells array is unique in requiring flexible queries:

```sql
-- This query is EASY with separate table:
SELECT spot_id FROM fact_swells WHERE period > 12 AND impact > 0.3

-- This query is HARD with 42 columns:
SELECT spot_id FROM fact_wave
WHERE (swell_0_period > 12 AND swell_0_impact > 0.3)
   OR (swell_1_period > 12 AND swell_1_impact > 0.3)
   OR (swell_2_period > 12 AND swell_2_impact > 0.3)
   OR ...
```

### Why Filter Zero-Height Swells?

Original data has 6 swells per wave entry, but typically only 1-3 are active:

```json
"swells": [
  { "height": 0, ... },   // inactive - FILTERED
  { "height": 3.4, ... }, // active - KEPT
  { "height": 2.7, ... }, // active - KEPT
  { "height": 0, ... },   // inactive - FILTERED
  { "height": 0, ... },   // inactive - FILTERED
  { "height": 0, ... }    // inactive - FILTERED
]
```

Filtering reduces `fact_swells` from ~720 to ~240 rows per scrape (~67% storage reduction).

---

## Storage Estimates

### Per Spot Per Scrape

| Table | Rows | Estimated Size (Parquet) |
|-------|------|--------------------------|
| fact_rating | 120 | ~5 KB |
| fact_wave | 120 | ~15 KB |
| fact_swells | ~240 | ~12 KB |
| fact_wind | 120 | ~8 KB |
| fact_weather | 384 | ~15 KB |
| fact_tides | 168 | ~8 KB |
| dim_sunlight | 16 | ~2 KB |
| **Total** | ~1,168 | **~65 KB** |

### At Scale

| Scale | Raw Size | Compressed (Parquet) | S3 Cost/Month |
|-------|----------|----------------------|---------------|
| 100 spots × 1 year | 2.4 GB | ~0.8-1.2 GB | ~$0.03 |
| 1,000 spots × 1 year | 24 GB | ~8-12 GB | ~$0.25 |
| 10,000 spots × 1 year | 240 GB | ~80-120 GB | ~$2.50 |

### Comparison to Raw JSON

- Raw JSON per scrape: ~380 KB (gzipped: ~50-60 KB)
- Parquet per scrape: ~65 KB
- Parquet is slightly larger than gzipped JSON but offers columnar query benefits

---

## Appendix: Data Type Reference

### Timestamp Handling

All timestamps in source data are Unix epoch (seconds). Convert during ETL:

```python
from datetime import datetime

# Source: 1768608000 (Unix epoch)
# Target: TIMESTAMP '2026-01-17 00:00:00'
ts = datetime.utcfromtimestamp(1768608000)
```

### String Enums

| Field | Possible Values |
|-------|----------------|
| rating_key | FLAT, VERY_POOR, POOR, POOR_TO_FAIR, FAIR, FAIR_TO_GOOD, GOOD, GOOD_TO_EPIC, EPIC |
| tide_type | NORMAL, HIGH, LOW |
| direction_type | Offshore, Onshore, Crosswind, Cross-offshore, Cross-onshore |
| condition (weather) | NIGHT_CLEAR, NIGHT_BRIEF_SHOWERS_POSSIBLE, DAY_PARTLY_CLOUDY, etc. |

### Units Reference

| Field | Unit | Source Location |
|-------|------|-----------------|
| surf_min, surf_max, height (swell) | Feet | wave.associated.units.waveHeight |
| temperature | Celsius | weather.associated.units.temperature |
| speed, gust | MPH | wind.associated.units.windSpeed |
| height (tide) | Meters | tides.associated.units.tideHeight |
| direction | Degrees (0-360) | N/A |
| period | Seconds | N/A |
| pressure | Millibars | N/A |
