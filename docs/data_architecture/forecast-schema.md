# Forecast Schema

> **Status: IMPLEMENTED** | Last verified: 2026-03-06

## Schema Diagram

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

## Table Definitions

### fact_rating

| Column | Type | Source Path | Notes |
|--------|------|-------------|-------|
| spot_id | STRING | metadata.spot_id | Primary key component |
| forecast_ts | TIMESTAMP | rating.data.rating[].timestamp | Converted from Unix epoch |
| scrape_ts | TIMESTAMP | metadata.timestamp | When the forecast was scraped |
| rating_key | STRING | rating.data.rating[].rating.key | "FAIR", "GOOD", "FAIR_TO_GOOD" |
| rating_value | FLOAT64 | rating.data.rating[].rating.value | 0-6 |
| utc_offset | INT32 | rating.data.rating[].utcOffset | Hours from UTC |
| location_lon | FLOAT64 | rating.associated.location.lon | Spot longitude |
| location_lat | FLOAT64 | rating.associated.location.lat | Spot latitude |
| run_init_ts | TIMESTAMP | rating.associated.runInitializationTimestamp | Model run time |

**Row count per scrape:** 120 (hourly for 5 days)

---

### fact_wave

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

### fact_swells (normalized from wave)

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

### fact_wind

| Column | Type | Source Path | Notes |
|--------|------|-------------|-------|
| spot_id | STRING | metadata.spot_id | |
| forecast_ts | TIMESTAMP | wind.data.wind[].timestamp | |
| scrape_ts | TIMESTAMP | metadata.timestamp | |
| speed | FLOAT64 | wind.data.wind[].speed | MPH |
| gust | FLOAT64 | wind.data.wind[].gust | MPH |
| direction | FLOAT64 | wind.data.wind[].direction | Degrees (0-360) |
| direction_type | STRING | wind.data.wind[].directionType | "Offshore", "Onshore", "Cross-shore" |
| optimal_score | INT32 | wind.data.wind[].optimalScore | |
| utc_offset | INT32 | wind.data.wind[].utcOffset | |
| location_lon | FLOAT64 | wind.associated.location.lon | |
| location_lat | FLOAT64 | wind.associated.location.lat | |
| run_init_ts | TIMESTAMP | wind.associated.runInitializationTimestamp | |

**Row count per scrape:** 120

---

### fact_weather

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

### fact_tides

| Column | Type | Source Path | Notes |
|--------|------|-------------|-------|
| spot_id | STRING | metadata.spot_id | |
| forecast_ts | TIMESTAMP | tides.data.tides[].timestamp | May be non-hourly |
| scrape_ts | TIMESTAMP | metadata.timestamp | |
| tide_type | STRING | tides.data.tides[].type | "NORMAL", "HIGH", "LOW" |
| height | FLOAT64 | tides.data.tides[].height | Feet |
| utc_offset | INT32 | tides.data.tides[].utcOffset | |
| tide_location_name | STRING | tides.associated.tideLocation.name | Tide station name |
| tide_location_lon | FLOAT64 | tides.associated.tideLocation.lon | Different from spot! |
| tide_location_lat | FLOAT64 | tides.associated.tideLocation.lat | |
| tide_location_min | FLOAT64 | tides.associated.tideLocation.min | Min possible height |
| tide_location_max | FLOAT64 | tides.associated.tideLocation.max | Max possible height |
| tide_location_mean | FLOAT64 | tides.associated.tideLocation.mean | |

**Row count per scrape:** 168 (irregular intervals, includes HIGH/LOW events)

---

### dim_sunlight

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

## Original Data Samples

For full examples of each forecast type's raw JSON structure, see the [Data Layer Overview](README.md) and sample data in `data/forecast/`.

### Rating (120 rows per scrape, hourly for 5 days)

```json
{
  "rating": {
    "associated": {
      "location": { "lon": -3.728, "lat": 51.488 },
      "runInitializationTimestamp": 1768608000
    },
    "data": {
      "rating": [
        {
          "timestamp": 1768608000,
          "utcOffset": 0,
          "rating": { "key": "FAIR", "value": 3 }
        }
      ]
    }
  }
}
```

### Wave (120 rows per scrape, hourly for 5 days) — MOST COMPLEX

- **Deepest nesting**: `surf.raw.min`, `surf.raw.max`
- **Three location references**: `location`, `forecastLocation`, `offshoreLocation`
- **swells array**: Always 6 elements, many with height=0 (inactive swells)
- Each swell has 7 fields: height, period, impact, power, direction, directionMin, optimalScore

### Sunlight (16 rows per scrape, daily for 16 days)

- No `timestamp` field — uses `midnight` as the anchor
- Each marker has its own UTC offset (for DST handling)

### Tides (168 rows per scrape, irregular intervals over 6 days)

- `tideLocation` is DIFFERENT from the spot location (references a tide station)
- `type` indicates tide state: "NORMAL", "HIGH", "LOW"
- Irregular timestamps (HIGH/LOW events inserted between hourly NORMAL readings)

### Weather (384 rows per scrape, hourly for 16 days)

- **Two data arrays**: `sunlightTimes` (duplicated from sunlight type) + `weather`
- Temperature in Celsius, pressure in millibars

### Wind (120 rows per scrape, hourly for 5 days)

- `directionType` enum: "Offshore", "Onshore", "Cross-shore", "Cross-offshore", "Cross-onshore"
- Nullable fields: `windStation`, `lastObserved` (for observed vs forecast data)

---

## Data Type Reference

### Timestamp Handling

All timestamps in source data are Unix epoch (seconds). Convert during ETL:

```python
from datetime import datetime, timezone

# Source: 1768608000 (Unix epoch)
# Target: TIMESTAMP '2026-01-17 00:00:00'
ts = datetime.fromtimestamp(1768608000, tz=timezone.utc)
```

### String Enums

| Field | Possible Values |
|-------|----------------|
| rating_key | FLAT, VERY_POOR, POOR, POOR_TO_FAIR, FAIR, FAIR_TO_GOOD, GOOD, EPIC |
| tide_type | NORMAL, HIGH, LOW |
| direction_type | Offshore, Onshore, Cross-shore, Cross-offshore, Cross-onshore |
| condition (weather) | NIGHT_CLEAR, NIGHT_BRIEF_SHOWERS_POSSIBLE, DAY_PARTLY_CLOUDY, etc. |

### Units Reference

| Field | Unit | Source Location |
|-------|------|-----------------|
| surf_min, surf_max, height (swell) | Feet | wave.associated.units.waveHeight |
| temperature | Celsius | weather.associated.units.temperature |
| speed, gust | MPH | wind.associated.units.windSpeed |
| height (tide) | Feet | tides.associated.units.tideHeight |
| direction | Degrees (0-360) | N/A |
| period | Seconds | N/A |
| pressure | Millibars | N/A |
