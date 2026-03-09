# System Overview

> **Status: IMPLEMENTED** (current scrapers/infrastructure) | **PLANNED** (layered storage rework) | Last verified: 2026-03-08

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
    raw/sitemap/       raw/taxonomy/        processed/discovery/
    {date}/...         {date}/...           latest/ + changes/ + snapshots/

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
| [Taxonomy Scraper](../scrapers/taxonomy-scraper.md) | Scheduled | Disabled | Recursively walks Surfline geographic hierarchy |
| Spot Reconciler | Scheduled | Disabled | Merges raw sitemap + taxonomy into processed discovery snapshots and change feeds |
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
