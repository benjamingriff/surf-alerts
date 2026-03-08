# Implementation Guide

> **Status: PLANNED** | Not yet implemented

## Database Architecture

### Hybrid Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                         API Layer                               │
│                    (FastAPI + Lambda)                            │
└───────────────────┬─────────────────────┬───────────────────────┘
                    │                     │
                    ▼                     ▼
    ┌───────────────────────┐   ┌───────────────────────┐
    │    Current Forecast   │   │   Historical Data     │
    │    (PostgreSQL /      │   │   (Parquet on S3 +    │
    │     Aurora Serverless)│   │    DuckDB / Athena)   │
    └───────────┬───────────┘   └───────────┬───────────┘
                │                           │
                └─────────────┬─────────────┘
                              │
                    ┌─────────┴─────────┐
                    │     ETL Job       │
                    │  (Scrape → Both)  │
                    └─────────┬─────────┘
                              │
                    ┌─────────┴─────────┐
                    │   Raw JSON (S3)   │
                    │   from Scrapers   │
                    └───────────────────┘
```

### Current Forecast Layer (PostgreSQL)

For low-latency current forecast queries:

**Why PostgreSQL over DynamoDB:**
- Natural joins between forecast types (wave + wind + rating)
- SQL functions for unit conversion and aggregations
- Better fit for computed endpoints (best windows, daily summary)
- Easier development and debugging
- Aurora Serverless for cost-effective scaling

**Schema approach:**
- Materialized view of "current" forecast (latest scrape only)
- Refresh on each new scrape
- Index on `(spot_id, forecast_ts)`
- TTL cleanup for old data

### Historical Data Layer (Parquet + DuckDB)

For analytical queries and historical access:

**Why Parquet on S3:**
- Cost-effective storage (~$0.023/GB/month)
- Columnar format optimized for analytical queries
- Works with DuckDB (fast, in-process), Athena (serverless), pandas
- Immutable data — perfect for long-term caching

**Partitioning strategy:**
```
s3://surf-alerts-data/forecasts/
  fact_rating/
    year=2026/
      month=01/
        spot_id=584204204e65fad6a77090d2/
          data_20260117.parquet
```

### Caching Layer

For sub-10ms response times on popular spots:

- **CloudFront** — Edge caching for static responses
- **ElastiCache (Redis)** — Computed aggregates (daily summaries, best windows)

---

## Technology Stack

| Layer | Technology | Rationale |
|-------|------------|-----------|
| API Framework | FastAPI (Python) | Async, auto OpenAPI docs, Pydantic validation |
| Hosting | Lambda + API Gateway | Serverless, scales to zero, pay-per-request |
| Current DB | Aurora Serverless v2 | PostgreSQL compatibility, auto-scaling |
| Historical DB | Parquet + DuckDB | Cost-effective, analytical queries |
| Cache | CloudFront + ElastiCache | Edge caching + computed aggregates |
| Auth | API Gateway API keys | Simple, built-in rate limiting |

---

## Authentication and Rate Limiting

**Note:** Data scraping from Surfline uses no authentication — all endpoints are public free-tier.

### Phase 1: Internal API

Simple API key authentication for internal use:

```http
GET /spots/584204204e65fad6a77090d2/forecast
X-API-Key: your-api-key-here
```

- API keys issued manually
- No rate limiting
- Internal documentation only

### Phase 2: Public API

Full API key management with rate limiting:

```http
GET /spots/584204204e65fad6a77090d2/forecast
Authorization: Bearer your-api-key-here
```

#### Rate Limits

| Tier | Requests/Hour | Requests/Day | History Access |
|------|---------------|--------------|----------------|
| Free | 100 | 1,000 | 7 days |
| Basic | 1,000 | 10,000 | 30 days |
| Pro | 10,000 | 100,000 | Full |
| Enterprise | Custom | Custom | Full |

---

## ETL Pipeline

```
Scraper Lambda
    │
    ▼
Raw JSON (S3)
    │
    ├──▶ PostgreSQL (current forecast, last scrape only)
    │      - Upsert by (spot_id, forecast_ts)
    │      - Delete forecasts older than 7 days
    │
    └──▶ Parquet (historical archive)
           - Append to partitioned files
           - Partitioned by year/month/spot_id
```

---

## API Project Structure

```
packages/api/
├── src/
│   └── forecast_api/
│       ├── __init__.py
│       ├── main.py              # FastAPI app entry point
│       ├── config.py            # Settings and configuration
│       ├── dependencies.py      # Dependency injection
│       ├── routers/
│       │   ├── spots.py         # /spots endpoints
│       │   ├── forecast.py      # /spots/{id}/forecast endpoints
│       │   ├── history.py       # /spots/{id}/history endpoints
│       │   └── discovery.py     # /forecast/compare, /forecast/discover
│       ├── services/
│       │   ├── forecast.py      # Forecast business logic
│       │   ├── history.py       # Historical queries
│       │   ├── accuracy.py      # Accuracy calculations
│       │   └── discovery.py     # Regional search logic
│       ├── repositories/
│       │   ├── postgres.py      # PostgreSQL queries
│       │   └── parquet.py       # Parquet/DuckDB queries
│       ├── models/
│       │   ├── spot.py          # Pydantic models for spots
│       │   ├── forecast.py      # Pydantic models for forecasts
│       │   └── errors.py        # Error response models
│       └── utils/
│           ├── units.py         # Unit conversion functions
│           └── pagination.py    # Cursor pagination helpers
├── tests/
│   ├── unit/
│   ├── integration/
│   └── e2e/
├── pyproject.toml
└── Dockerfile
```

---

## Verification Plan

When implemented, verify with these tests:

### 1. Current Forecast Accuracy

Compare `/spots/{id}/forecast` response against raw scraped JSON.

### 2. Unit Conversion

Request same endpoint with `?units=metric` and `?units=imperial`, verify conversion factors.

### 3. Historical Retrieval

Request `/spots/{id}/history?from=...&to=...` and verify data matches Parquet.

### 4. Best Windows Logic

Verify every hour in returned windows meets all filter criteria.

### 5. Multi-Spot Compare

Ensure rankings are consistent with individual spot forecasts.

### 6. Caching Behavior

Verify ETag headers change only when new scrape arrives.

---

## OpenAPI Specification

When implemented, the API will provide an OpenAPI 3.0 specification at:

```
GET /openapi.json
GET /docs          # Swagger UI
GET /redoc         # ReDoc
```
