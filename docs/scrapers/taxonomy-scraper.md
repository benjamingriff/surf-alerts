# Taxonomy Scraper

> **Status: IMPLEMENTED** | Currently disabled in infrastructure | Legacy discovery path

Recursively walks the Surfline geographic hierarchy (Earth > Continents > Countries > Regions > Subregions > Spots). EventBridge-triggered scheduled Lambda with 10-minute timeout.

**Package:** `packages/scrapers/taxonomy_scraper/`

> **Architecture note:** This scraper is not part of the active target discovery flow. The target flow uses sitemap for spot-universe detection and spot reports for rich metadata.

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

## Current Role

This scraper remains documented because the package exists and may still be useful for research, backfills, or geographic enrichment. It is not the planned source of truth for live discovery.

The target discovery architecture instead uses:

- sitemap-driven `added` / `removed` detection
- spot-report-driven checksum changes
- append-only Parquet version tables in `processed/discovery/`
- a derived `catalog_latest/` snapshot for operational reads

See [Surfline Taxonomy & Search](../surfline/taxonomy-and-search.md) for the taxonomy API details and [Storage Layout](../data_architecture/storage-layout.md) for the target bucket structure.
