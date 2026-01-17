# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Surf-alerts is a serverless Python/TypeScript project that scrapes surf forecast data from Surfline and stores it in AWS S3. The project uses AWS CDK for infrastructure and GitHub Actions for CI/CD.

## Commands

### Python (UV package manager)

```bash
# Install all dependencies
uv sync

# Run all tests
pytest

# Run tests for specific package
pytest packages/scrapers/forecast_scraper

# Run single test file
pytest packages/scrapers/forecast_scraper/tests/smoke/test_scrape_forecast_live.py -v

# Lint with ruff
ruff check .
```

### Infrastructure (AWS CDK)

```bash
cd infrastructure

# Install dependencies
npm ci

# Build TypeScript
npm run build

# Run CDK tests
npm test

# Synthesize CloudFormation
npx cdk synth

# Deploy
npx cdk deploy SufAlertsStack --require-approval never
```

## Architecture

### Monorepo Structure

The project uses UV workspaces for Python packages:

- **packages/scrapers/forecast_scraper** - Scrapes surf forecast data from 6 Surfline API endpoints (rating, sunlight, tides, wave, weather, wind)
- **packages/scrapers/spot_scraper** - Scrapes spot/beach location data with modular handlers (sitemap_scraper, spot_processor, spot_updater)
- **packages/jobs/dispatcher** - Job orchestration (placeholder)
- **packages/migrations/archive_legacy_data** - Data migration utilities
- **infrastructure/** - AWS CDK TypeScript infrastructure

### Scraper Pattern

Each scraper follows this module structure:
```
src/{scraper_name}/
├── handler.py          # Lambda entry point, processes SQS messages
├── scraper/core.py     # Core scraping logic
├── http/client.py      # HTTP client with retry logic (uses curl-cffi for bot evasion)
├── parser/response.py  # JSON response parsing
├── io/s3.py           # S3 writer with gzip compression
└── logger/logger.py   # AWS Powertools logging wrapper
```

### Infrastructure Components

- **ScraperWorker** construct: Creates Lambda function (Docker-based) with SQS trigger
- **SqsQueue** construct: SQS queue with dead-letter queue (3 retries, 7-day DLQ retention)
- Lambda config: 60s timeout, 1024MB memory, batch size 1, max concurrency 2

### Key Dependencies

- `curl-cffi` - HTTP client that impersonates Chrome browser to bypass anti-bot protection
- `aws-lambda-powertools` - AWS Lambda logging, tracing, metrics
- `moto` - AWS service mocking for tests

## Testing

Tests use pytest with moto for AWS mocking. The root `conftest.py` provides:
- Mocked S3 bucket fixture
- AWS credential environment variables
- Suppressed verbose boto/httpcore logging

## CI/CD

GitHub Actions deploys on push to `main` using OIDC authentication (no static AWS keys). The workflow synthesizes and deploys the CDK stack.
