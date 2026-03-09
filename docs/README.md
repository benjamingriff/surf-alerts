# Surf Alerts

Personal surf forecast data platform. Scrapes surf and spot data from Surfline, stores it in S3, and is evolving toward a layered raw/processed storage model with event-driven downstream processing.

## Status Dashboard

| Component | Status | Notes |
|-----------|--------|-------|
| **Forecast Scraper** | IMPLEMENTED | 6 endpoints, Docker Lambda, SQS trigger |
| **Spot Scraper** | IMPLEMENTED | `/reports` spot metadata collection |
| **Infrastructure (CDK)** | IMPLEMENTED | Lambda, SQS, S3, GitHub Actions CI/CD |
| **Data Storage Architecture** | PLANNED | Partial medallion design: `raw/`, `processed/`, `control/` |
| **Discovery Data Model** | PLANNED | Append-only Parquet version tables plus derived latest catalog |
| **Forecast Data Model** | IMPLEMENTED | Forecast analytics schema, 7 fact/dim tables |
| **Surfline API Reference** | IMPLEMENTED | 16 endpoints documented, verified 2026-03-06 |
| **API Design** | PLANNED | 10 endpoints designed, FastAPI + DuckDB |
| **Legacy Data Migration** | PLANNED | 1TB+ JSON to Parquet, ~$6-8 estimated cost |
| **CLI** | PLANNED | Not started |
| **Dispatcher** | PLANNED | Job orchestration, not started |
| **Discovery Processors** | PLANNED | `discovery_diff`, `spot_report_processor`, `catalog_builder` |
| **Frontend** | PLANNED | Not started |
| **API Package** | PLANNED | Not started |

## Quick Links

- [Architecture Overview](architecture/README.md) — how the system fits together
- [Scraper Pattern](scrapers/README.md) — shared module structure for all scrapers
- [Surfline API Reference](surfline/README.md) — all discovered Surfline endpoints
- [Data Layer Overview](data_architecture/README.md) — storage architecture and layer model
- [Storage Layout](data_architecture/storage-layout.md) — prefixes, retention, and event boundaries
- [Discovery Schema](data_architecture/discovery-schema.md) — versioned Parquet discovery tables
- [Discovery Transformations](data_architecture/discovery-transformations.md) — checksums, events, and latest catalog builds
- [Forecast Schema](data_architecture/forecast-schema.md) — forecast analytics schema design
- [API Design](api/README.md) — planned REST API spec

## Project Structure

```
surf-alerts/
├── packages/
│   ├── scrapers/
│   │   ├── forecast_scraper/    # 6-endpoint forecast data scraper
│   │   └── spot_scraper/        # Spot metadata + sitemap scraper
│   ├── jobs/
│   │   ├── dispatcher/          # Job orchestration (planned)
│   │   └── spot_reconciler/     # Legacy discovery job, planned for replacement
│   └── migrations/
│       └── archive_legacy_data/ # Data migration utilities
├── infrastructure/              # AWS CDK (TypeScript)
├── docs/                        # This documentation site
└── data/                        # Sample scraped data
```
