# Forecast Endpoints

> **Status: IMPLEMENTED** | Last verified: 2026-03-06

All forecast endpoints share common parameters:

| Param | Required | Description |
|-------|----------|-------------|
| `spotId` | Yes | Surfline spot ID |
| `days` | No | Number of forecast days (default varies by endpoint) |
| `intervalHours` | No | Data interval in hours (1, 3, 6, etc.) |
| `cacheEnabled` | No | Enable server-side caching (`true`/`false`) |

---

## GET /kbyg/spots/forecasts/rating

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

---

## GET /kbyg/spots/forecasts/wave

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
- `surf.min`/`surf.max` — combined surf height range
- `surf.humanRelation` — human-readable size ("Knee to waist", "Overhead", etc.)
- `swells[]` — individual swell components with height, period, and direction
- `power` — wave energy metric

---

## GET /kbyg/spots/forecasts/wind

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
- `speed` — sustained wind speed
- `gust` — gust speed
- `direction` — wind direction in degrees
- `directionType` — relation to break: `Offshore`, `Cross-shore`, `Onshore`, `Cross-offshore`, `Cross-onshore`
- `optimalScore` — 0 (bad) to 2 (optimal)

---

## GET /kbyg/spots/forecasts/tides

Tide heights and high/low markers.

```
GET /kbyg/spots/forecasts/tides?spotId={spotId}&days=6&cacheEnabled=true&units[tideHeight]=FT
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

**Note:** No `intervalHours` parameter — tide data comes at natural high/low points plus interpolated values.

---

## GET /kbyg/spots/forecasts/weather

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

## GET /kbyg/spots/forecasts/sunlight

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

## GET /kbyg/spots/forecasts/surf

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

## GET /kbyg/spots/forecasts/conditions

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
- `observation` — human-written forecast text from Surfline forecaster
- `am`/`pm` — separate morning and afternoon forecasts
- `dayToWatch` — boolean flag for standout days

**Note:** No `intervalHours` parameter — returns one entry per day with AM/PM split.
