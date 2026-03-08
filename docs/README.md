# Surf Alerts

Personal surf forecast data platform. Scrapes forecast data from Surfline, stores it in S3, and (planned) serves it via a custom API.

## Status Dashboard

| Component | Status | Notes |
|-----------|--------|-------|
| **Forecast Scraper** | IMPLEMENTED | 6 endpoints, Docker Lambda, SQS trigger |
| **Spot Scraper** | IMPLEMENTED | Sitemap parsing + spot data collection |
| **Infrastructure (CDK)** | IMPLEMENTED | Lambda, SQS, S3, GitHub Actions CI/CD |
| **Forecast Data Model** | IMPLEMENTED | Star schema design, 7 fact/dim tables |
| **Surfline API Reference** | IMPLEMENTED | 16 endpoints documented, verified 2026-03-06 |
| **API Design** | PLANNED | 10 endpoints designed, FastAPI + DuckDB |
| **Legacy Data Migration** | PLANNED | 1TB+ JSON to Parquet, ~$6-8 estimated cost |
| **CLI** | PLANNED | Not started |
| **Dispatcher** | PLANNED | Job orchestration, not started |
| **Spot Reconciler** | PLANNED | Not started |
| **Frontend** | PLANNED | Not started |
| **API Package** | PLANNED | Not started |

## Quick Links

- [Architecture Overview](architecture/README.md) — how the system fits together
- [Scraper Pattern](scrapers/README.md) — shared module structure for all scrapers
- [Surfline API Reference](surfline/README.md) — all discovered Surfline endpoints
- [Forecast Schema](data_architecture/forecast-schema.md) — Parquet star schema design
- [API Design](api/README.md) — planned REST API spec

## Project Structure

```
surf-alerts/
├── packages/
│   ├── scrapers/
│   │   ├── forecast_scraper/    # 6-endpoint forecast data scraper
│   │   └── spot_scraper/        # Spot metadata + sitemap scraper
│   ├── jobs/
│   │   └── dispatcher/          # Job orchestration (planned)
│   └── migrations/
│       └── archive_legacy_data/ # Data migration utilities
├── infrastructure/              # AWS CDK (TypeScript)
├── docs/                        # This documentation site
└── data/                        # Sample scraped data
```
