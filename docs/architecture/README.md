# System Overview

> **Status: IMPLEMENTED** (current scrapers/infrastructure) | **PLANNED** (layered storage and discovery rework) | Last verified: 2026-03-08

## Component Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                    Scheduled (EventBridge)                       │
│                    Discovery entrypoint                          │
└─────────────────────────────────────────────────────────────────┘
         │
         ▼
  ┌──────────────┐
  │   Sitemap    │
  │   Scraper    │
  │  06:00 UTC   │
  └──────┬───────┘
         │
         ▼
    raw/sitemap/{date}/...
         │
         ▼
  ┌────────────────────┐
  │  Discovery Diff    │
  │  Lambda (planned)  │
  └──────┬─────────────┘
         │
         ├──────────────▶ processed/discovery/events/...
         └──────────────▶ SQS queue for spot scraper

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
  raw/spot_report/...                 raw/forecast/...
         │                                      │
         ▼                                      ▼
  Spot Report Processor                Forecast Processors
     (planned)                           (planned)
         │                                      │
         ▼                                      ▼
  processed/discovery/...             processed/forecast/...

                         │
                         ▼
              ┌─────────────────────┐
              │  S3 Data Bucket      │
              │  {stack}-data        │
              │ raw/ processed/      │
              │ control/             │
              └─────────────────────┘
```

## Components

| Component | Type | Status | Description |
|-----------|------|--------|-------------|
| [Forecast Scraper](../scrapers/forecast-scraper.md) | SQS Worker | Active | Scrapes 6 Surfline forecast endpoints per spot |
| [Spot Scraper](../scrapers/spot-scraper.md) | SQS Worker | Active | Scrapes spot metadata from `/reports` endpoint |
| [Sitemap Scraper](../scrapers/sitemap-scraper.md) | Scheduled | Disabled | Parses Surfline sitemap XML for spot discovery |
| Discovery Diff | S3/EventBridge Lambda | Planned | Compares sitemap IDs to current catalog and emits `added` / `removed` events |
| Spot Report Processor | S3 Lambda | Planned | Computes checksums and appends new discovery versions from raw spot reports |
| Catalog Builder | S3/Manifest Lambda | Planned | Rebuilds `processed/discovery/catalog_latest/` from version tables |
| [Taxonomy Scraper](../scrapers/taxonomy-scraper.md) | Scheduled | Disabled | Legacy discovery path, not part of the target flow |
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
| Storage | S3 (`raw/`, `processed/`, `control/`) |
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

Planned additions to the workspace for the target discovery flow:

- `packages/jobs/discovery_diff`
- `packages/jobs/spot_report_processor`
- `packages/jobs/catalog_builder`
