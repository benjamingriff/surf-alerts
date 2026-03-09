# Sitemap Scraper

> **Status: IMPLEMENTED** | Currently disabled in infrastructure

Parses the Surfline XML sitemap to discover all surf spots and their IDs. EventBridge-triggered scheduled Lambda.

**Package:** `packages/scrapers/sitemap_scraper/`

> **Storage note:** The raw-layer path below describes the target storage contract after the layered storage rework.

## Endpoint Scraped

```
GET https://www.surfline.com/sitemaps/spots.xml
```

## How It Works

1. Triggered by EventBridge cron (06:00 UTC, currently disabled)
2. Fetches the XML sitemap from `www.surfline.com`
3. Parses XML with `lxml`
4. Extracts spot IDs from URLs using regex: `surfline.com/surf-report/[name]/([spot_id])(/forecast)?`
5. Writes raw sitemap results to S3

In the target architecture, the sitemap is the **source of the live spot universe**. It is not joined with taxonomy during normal processing.

## URL Pattern

The sitemap contains two URL types per spot:

```xml
<url>
  <loc>https://www.surfline.com/surf-report/rest-bay/584204204e65fad6a77090d2</loc>
</url>
<url>
  <loc>https://www.surfline.com/surf-report/rest-bay/584204204e65fad6a77090d2/forecast</loc>
</url>
```

Both are captured — the main report URL and the forecast URL.

## Raw Output Format

Written to:

```text
raw/sitemap/scrape_date=YYYY-MM-DD/run_id=<run_id>.json.gz
```

Payload shape:

```json
{
  "584204204e65fad6a77090d2": {
    "spot_id": "584204204e65fad6a77090d2",
    "link": "https://www.surfline.com/surf-report/rest-bay/584204204e65fad6a77090d2",
    "forecast": "https://www.surfline.com/surf-report/rest-bay/584204204e65fad6a77090d2/forecast"
  }
}
```

These fields are enough to:

- detect new spot IDs
- detect missing spot IDs
- preserve the latest known report and forecast URLs
- enqueue new IDs for spot metadata scraping

## Additional Dependencies

- `lxml` — XML parsing (not used by other scrapers)

## Infrastructure

| Setting | Value |
|---------|-------|
| Trigger | EventBridge cron: 06:00 UTC |
| Timeout | 60s |
| Status | Disabled |

## Planned Downstream Flow

Raw sitemap ingestion should trigger a `discovery_diff` processor which:

1. Reads the current latest catalog from `processed/discovery/catalog_latest/`
2. Compares the new sitemap ID set against current live `spot_id`s
3. Appends `added` and `removed` events to `processed/discovery/events/...`
4. Queues `added` IDs for spot report scraping

Most `changed` events do not come from the sitemap. They come later from spot report refreshes and checksum comparison.

Taxonomy is not part of the active target discovery flow.

See [Surfline Taxonomy & Search](../surfline/taxonomy-and-search.md) for the sitemap API details and [Storage Layout](../data_architecture/storage-layout.md) for the target bucket structure.
