# Package Index

> **Status: IMPLEMENTED / PLANNED** | Last verified: 2026-03-08

All packages are managed via UV workspaces from the root `pyproject.toml`.

## Package Status

| Package | Path | Status | Description |
|---------|------|--------|-------------|
| [Forecast Scraper](../scrapers/forecast-scraper.md) | `packages/scrapers/forecast_scraper` | IMPLEMENTED | Scrapes 6 forecast endpoints per spot |
| [Spot Scraper](../scrapers/spot-scraper.md) | `packages/scrapers/spot_scraper` | IMPLEMENTED | Scrapes spot metadata from `/reports` |
| [Sitemap Scraper](../scrapers/sitemap-scraper.md) | `packages/scrapers/sitemap_scraper` | IMPLEMENTED | Parses Surfline sitemap XML |
| [Taxonomy Scraper](../scrapers/taxonomy-scraper.md) | `packages/scrapers/taxonomy_scraper` | IMPLEMENTED | Legacy geographic hierarchy scraper |
| [Discovery Processors](discovery-processors.md) | `packages/jobs/discovery_*` | PLANNED | Sitemap diff, spot report processing, latest catalog build |
| [Forecast Processors](forecast-processors.md) | `packages/jobs/forecast_*` | PLANNED | Batch planning, completion detection, canonical forecast processing |
| [Spot Reconciler (legacy)](spot-reconciler.md) | `packages/jobs/spot_reconciler` | IMPLEMENTED | Earlier sitemap + taxonomy reconciliation approach |
| [Archive Legacy Data](archive-legacy-data.md) | `packages/migrations/archive_legacy_data` | IMPLEMENTED | Data migration utilities |
| [Dispatcher](dispatcher.md) | `packages/jobs/dispatcher` | PLANNED | Job orchestration |
| [CLI](cli.md) | `packages/cli` | PLANNED | Command-line interface |
| [Frontend](frontend.md) | — | PLANNED | Web UI |
| [API Package](api-package.md) | `packages/api` | PLANNED | REST API (FastAPI) |

## Shared Dependencies

| Dependency | Version | Used By |
|------------|---------|---------|
| `aws-lambda-powertools` | >= 3.23.0 | All scrapers and discovery jobs |
| `boto3` | >= 1.42.15 | All scrapers and discovery jobs |
| `curl-cffi` | >= 0.14.0 | All scrapers |
| `lxml` | — | Sitemap scraper |
| `timezonefinder` | — | Taxonomy scraper only |

## Dev Dependencies

| Dependency | Version | Purpose |
|------------|---------|---------|
| `pytest` | >= 9.0.2 | Testing |
| `moto` | >= 5.1.19 | AWS service mocking |
| `ruff` | — | Linting (line length: 100) |

## Commands

```bash
uv sync                    # Install all dependencies
pytest                     # Run all tests
pytest packages/scrapers/forecast_scraper  # Test single package
ruff check .               # Lint
```
