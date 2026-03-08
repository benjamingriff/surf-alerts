# Taxonomy & Search

> **Status: IMPLEMENTED** | Last verified: 2026-03-06

---

## GET /taxonomy (type=taxonomy)

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
- `contains[]` — child nodes at the next level
- `in[]` — parent nodes (geographic ancestry)
- `location.coordinates` — GeoJSON `[lng, lat]`

**Hierarchy levels:** `spot_type` (Earth) > `Admin1H` (continent) > `Country` > `Region` > `Subregion` > `spot`

**Root node:** `58f7ed51dadb30820bb38782` (Earth)

Our `taxonomy_scraper` recursively walks this tree starting from the root, with a 500ms delay between requests to avoid rate limiting.

---

## GET /taxonomy (type=spot)

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

## GET /search/site

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

## GET /sitemaps/spots.xml

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
