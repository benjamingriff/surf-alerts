# Taxonomy Scraper

> **Status: IMPLEMENTED** | Currently disabled in infrastructure

Recursively walks the Surfline geographic hierarchy (Earth > Continents > Countries > Regions > Subregions > Spots). EventBridge-triggered scheduled Lambda with 10-minute timeout.

**Package:** `packages/scrapers/taxonomy_scraper/`

> **Storage note:** The raw-layer path below describes the target storage contract after the layered storage rework.

## Endpoint Scraped

```
GET /taxonomy?type=taxonomy&id={taxonomyId}&maxDepth=0
```

Starting from the root node `58f7ed51dadb30820bb38782` (Earth), recursively fetches each node's children.

## How It Works

1. Triggered by EventBridge cron (06:00 UTC, currently disabled)
2. Fetches root taxonomy node (Earth)
3. For each child in `contains[]`, recursively fetches that node
4. Adds timezone info via `TimezoneFinder` reverse geocoding
5. Builds full hierarchical tree
6. Writes raw taxonomy data to S3

**Rate limiting:** 500ms delay between every request to avoid 429s. This is why the function has a 10-minute timeout — hundreds of sequential API calls.

## Hierarchy Levels

```
Earth (spot_type)
└── North America (Admin1H)
    └── United States (Country)
        └── California (Region)
            └── San Diego (Subregion)
                └── Blacks Beach (spot)
```

## Raw Output Format

Written to:

```text
raw/taxonomy/scrape_date=YYYY-MM-DD/run_id=<run_id>.json.gz
```

Payload shape:

```json
{
  "scraped_at": "2026-01-17T06:00:00Z",
  "taxonomy": {
    "tax_id": "58f7ed51dadb30820bb38782",
    "name": "Earth",
    "type": "spot_type",
    "lat": 0,
    "lng": 0,
    "timezone": "UTC",
    "utc_offset": 0,
    "contains": [
      {
        "tax_id": "...",
        "name": "North America",
        "type": "Admin1H",
        "lat": 40.0,
        "lng": -100.0,
        "timezone": "America/Chicago",
        "utc_offset": -6,
        "contains": [...]
      }
    ]
  }
}
```

Spot-level nodes include `spot_id` and `link` fields instead of `contains`.

## Additional Dependencies

- `timezonefinder` — Reverse geocoding coordinates to IANA timezone strings

## Infrastructure

| Setting | Value |
|---------|-------|
| Trigger | EventBridge cron: 06:00 UTC |
| Timeout | 600s (10 minutes) |
| Status | Disabled |

## Spot Reconciler

The **spot reconciler** (`packages/jobs/spot_reconciler/`) runs after the sitemap and taxonomy scrapers (06:15 UTC) and:

1. Reads raw sitemap data (`raw/sitemap/...`)
2. Reads raw taxonomy data (`raw/taxonomy/...`)
3. Reads previous latest state (`processed/discovery/latest/state.json.gz`)
4. Flattens taxonomy tree, merges with sitemap URLs
5. Computes SHA256 checksums on mutable fields (name, lat, lng, timezone, utc_offset, link)
6. Detects changes: added, removed, modified spots

**Outputs:**
- `processed/discovery/snapshots/...` — full current catalog snapshot
- `processed/discovery/changes/...` — change records
- `processed/discovery/latest/state.json.gz` — state snapshot for next run
- `processed/discovery/latest/catalog.json.gz` — latest catalog for readers

See [Surfline Taxonomy & Search](../surfline/taxonomy-and-search.md) for the taxonomy API details and [Storage Layout](../data_architecture/storage-layout.md) for the target bucket structure.
