# Sitemap Scraper

> **Status: IMPLEMENTED** | Currently disabled in infrastructure

Parses the Surfline XML sitemap to discover all surf spots and their IDs. EventBridge-triggered scheduled Lambda.

**Package:** `packages/scrapers/sitemap_scraper/`

## Endpoint Scraped

```
GET https://www.surfline.com/sitemaps/spots.xml
```

## How It Works

1. Triggered by EventBridge cron (06:00 UTC, currently disabled)
2. Fetches the XML sitemap from `www.surfline.com`
3. Parses XML with `lxml`
4. Extracts spot IDs from URLs using regex: `surfline.com/surf-report/[name]/([spot_id])(/forecast)?`
5. Writes results to S3

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

## Output Format

Written to `spots/{date}/sitemap.json.gz`:

```json
{
  "584204204e65fad6a77090d2": {
    "spot_id": "584204204e65fad6a77090d2",
    "link": "https://www.surfline.com/surf-report/rest-bay/584204204e65fad6a77090d2",
    "forecast": "https://www.surfline.com/surf-report/rest-bay/584204204e65fad6a77090d2/forecast"
  }
}
```

## Additional Dependencies

- `lxml` — XML parsing (not used by other scrapers)

## Infrastructure

| Setting | Value |
|---------|-------|
| Trigger | EventBridge cron: 06:00 UTC |
| Timeout | 60s |
| Status | Disabled |

See [Surfline Taxonomy & Search](../surfline/taxonomy-and-search.md) for the sitemap API details.
