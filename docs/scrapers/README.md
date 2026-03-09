# Scraper Pattern

> **Status: IMPLEMENTED** | Last verified: 2026-03-08

All scrapers follow a shared module structure. Each is a UV workspace package deployed as a Docker Lambda.

## Module Structure

```
packages/scrapers/{scraper_name}/
├── pyproject.toml
├── Dockerfile
├── src/{scraper_name}/
│   ├── __init__.py
│   ├── handler.py          # Lambda entry point
│   ├── scraper/core.py     # Core scraping logic
│   ├── http/client.py      # HTTP client with retry logic
│   ├── parser/response.py  # Response parsing
│   ├── io/s3.py            # S3 writer with gzip compression
│   └── logger/logger.py    # AWS Powertools logging wrapper
└── tests/
```

## Shared Dependencies

```toml
aws-lambda-powertools >= 3.23.0
boto3 >= 1.42.15
curl-cffi >= 0.14.0
```

## Handler Pattern

All SQS-triggered scrapers use the same handler pattern:

```python
def lambda_handler(event: dict, context: LambdaContext):
    for record in event["Records"]:
        body = json.loads(record["body"])
        spot_id = body["spot_id"]
        bucket = body["bucket"]
        prefix = body["prefix"]
        # scrape, parse, write to S3
```

**SQS message format:**
```json
{
  "spot_id": "584204204e65fad6a77090d2",
  "bucket": "sufalertsstack-data",
  "prefix": "raw/forecast/spot_id=584204204e65fad6a77090d2/scrape_date=2026-01-17/run_id=abc123"
}
```

## HTTP Client

All scrapers share the same `curl-cffi` HTTP client configuration:

| Setting | Value |
|---------|-------|
| Impersonator | Chrome (via curl-cffi) |
| Timeout | 30s per request |
| Max retries | 3 |
| Backoff | Exponential: 1s, 2s, 4s |
| Jitter | 0-1s random added to backoff |
| Rate limit handling | Detects 429, logs headers, retries with backoff |

**Required headers:**
```
Accept: application/json
Accept-Language: en-US,en;q=0.9
Referer: https://www.surfline.com/
Origin: https://www.surfline.com
```

## S3 Writer

All scrapers use the same S3Writer class:

- Automatic gzip compression (enabled by default)
- Content-Type: `application/json`
- Content-Encoding: `gzip`
- Auto-appends `.gz` suffix to key
- Returns S3 URI (`s3://bucket/key.gz`)

## Docker Build

All scrapers use the same multi-stage Docker pattern:

```dockerfile
# Stage 1: UV build
FROM ghcr.io/astral-sh/uv:0.9.4 AS uv-build
# Install dependencies with UV

# Stage 2: Lambda runtime
FROM public.ecr.aws/lambda/python:3.12
# Copy built packages, set PYTHONPATH
CMD ["scraper_name.handler.lambda_handler"]
```

## Logging

AWS Lambda Powertools structured logging. Service names:
- `forecast-scraper`
- `spot-scraper`
- `sitemap-scraper`
- `taxonomy-scraper`
- `spot-reconciler`

Log level controlled by `POWERTOOLS_LOG_LEVEL` environment variable (default: `INFO`).

## Scrapers

| Scraper | Trigger | Endpoints | Doc |
|---------|---------|-----------|-----|
| [Forecast Scraper](forecast-scraper.md) | SQS | 6 forecast APIs | Per-spot forecasts |
| [Spot Scraper](spot-scraper.md) | SQS | 1 reports API | Spot metadata |
| [Sitemap Scraper](sitemap-scraper.md) | EventBridge | Sitemap XML | Spot discovery |
| [Taxonomy Scraper](taxonomy-scraper.md) | EventBridge | Taxonomy API | Geographic hierarchy |
