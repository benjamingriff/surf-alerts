# Spot Endpoints

> **Status: IMPLEMENTED** | Last verified: 2026-03-06

---

## GET /kbyg/spots/reports

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

**Notes:** This is the richest spot endpoint. Our `spot_scraper` uses this as its primary data source. No `timezonefinder` needed — timezone comes directly from the API.

---

## GET /kbyg/spots/details

Minimal spot info — primarily name and associated metadata.

```
GET /kbyg/spots/details?spotId={spotId}
```

**Parameters:**
| Param | Required | Description |
|-------|----------|-------------|
| `spotId` | Yes | Surfline spot ID |

**Response:** Returns `associated` metadata and basic spot identification. Less data than `/reports` — mainly useful if you only need the spot name or timezone.

---

## GET /kbyg/spots/nearby

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

## GET /kbyg/regions/overview

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

## GET /kbyg/mapview

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
