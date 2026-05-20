# Surf Alerts

Serverless platform that scrapes surf forecast data from Surfline and stores it in AWS S3. Uses AWS CDK for infrastructure and GitHub Actions for CI/CD.

## Quick Start

```bash
# Install dependencies, including all workspace packages
uv sync --all-packages --dev

# Run tests with all workspace packages available
uv run --all-packages pytest

# Lint
uv run ruff check .
```

### Infrastructure

```bash
cd infrastructure
npm ci
npx cdk synth
npx cdk deploy SufAlertsStack --require-approval never
```

## Project Structure

```
packages/
├── scrapers/
│   ├── forecast_scraper/    # 6-endpoint forecast data scraper
│   ├── spot_scraper/        # Spot metadata scraper
│   ├── sitemap_scraper/     # Surfline sitemap parser
│   └── taxonomy_scraper/    # Geographic hierarchy walker
├── jobs/
│   ├── dispatcher/          # Job orchestration (planned)
│   └── spot_reconciler/     # Spot change detection
├── migrations/
│   └── archive_legacy_data/ # JSON → Parquet migration
├── cli/                     # CLI (planned)
├── frontend/                # Next.js frontend (planned)
infrastructure/              # AWS CDK (TypeScript)
docs/                        # Documentation (GitBook)
```

## Documentation

Full docs at [docs/](docs/README.md) — architecture, API reference, data model, and more.
