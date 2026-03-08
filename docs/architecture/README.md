# System Overview

> **Status: IMPLEMENTED** | Last verified: 2026-03-08

## Component Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                    Scheduled (EventBridge)                       │
│                    Currently disabled                            │
└─────────────────────────────────────────────────────────────────┘
         │                    │                        │
         ▼                    ▼                        ▼
  ┌──────────────┐   ┌───────────────┐      ┌─────────────────┐
  │   Sitemap    │   │   Taxonomy    │      │ Spot Reconciler  │
  │   Scraper    │   │   Scraper     │      │     (Job)        │
  │  06:00 UTC   │   │  06:00 UTC    │      │   06:15 UTC      │
  └──────┬───────┘   └──────┬────────┘      └────────┬─────────┘
         │                   │                        │
         ▼                   ▼                        ▼
     spots/              taxonomy/              spots/latest/
     {date}/             {date}/                state.json.gz
     sitemap.json.gz     taxonomy.json.gz       changes.json.gz

┌─────────────────────────────────────────────────────────────────┐
│                    SQS-Triggered Workers                        │
└─────────────────────────────────────────────────────────────────┘
         │                                      │
         ▼                                      ▼
  ┌──────────────┐                    ┌──────────────────┐
  │ Spot Scraper │                    │ Forecast Scraper  │
  │ (active)     │                    │ (active)          │
  │ concurrency:5│                    │ concurrency:2     │
  └──────┬───────┘                    └────────┬──────────┘
         │                                      │
         ▼                                      ▼
  S3: {prefix}.gz                     S3: {prefix}.gz
  (spot report)                       (6 forecast endpoints)

                         │
                         ▼
              ┌─────────────────────┐
              │  S3 Data Bucket     │
              │  {stack}-data       │
              │  Encrypted, RETAIN  │
              └─────────────────────┘
```

## Components

| Component | Type | Status | Description |
|-----------|------|--------|-------------|
| [Forecast Scraper](../scrapers/forecast-scraper.md) | SQS Worker | Active | Scrapes 6 Surfline forecast endpoints per spot |
| [Spot Scraper](../scrapers/spot-scraper.md) | SQS Worker | Active | Scrapes spot metadata from `/reports` endpoint |
| [Sitemap Scraper](../scrapers/sitemap-scraper.md) | Scheduled | Disabled | Parses Surfline sitemap XML for spot discovery |
| [Taxonomy Scraper](../scrapers/taxonomy-scraper.md) | Scheduled | Disabled | Recursively walks Surfline geographic hierarchy |
| Spot Reconciler | Scheduled | Disabled | Merges sitemap + taxonomy, detects spot changes |
| [Infrastructure](infrastructure.md) | CDK | Deployed | Lambda, SQS, S3, EventBridge |
| [CI/CD](../operations/ci-cd.md) | GitHub Actions | Active | OIDC deploy on push to main |

## Tech Stack

| Layer | Technology |
|-------|------------|
| Language | Python 3.12 |
| HTTP Client | curl-cffi (Chrome impersonation) |
| Logging | AWS Lambda Powertools |
| Infrastructure | AWS CDK (TypeScript) |
| Compute | Docker Lambda |
| Queuing | SQS with DLQ |
| Storage | S3 (gzip JSON) |
| Package Manager | UV workspaces |
| CI/CD | GitHub Actions + OIDC |

## UV Workspace Packages

```toml
[tool.uv.workspace]
members = [
    "packages/cli",
    "packages/jobs/dispatcher",
    "packages/jobs/spot_reconciler",
    "packages/migrations/archive_legacy_data",
    "packages/scrapers/forecast_scraper",
    "packages/scrapers/sitemap_scraper",
    "packages/scrapers/taxonomy_scraper",
    "packages/scrapers/spot_scraper",
]
```
