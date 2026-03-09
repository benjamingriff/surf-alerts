# Implementation Guide

> **Status: PLANNED** | Not yet implemented

## Storage And Query Architecture

### Hybrid Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                         API Layer                               │
│                    (FastAPI + Lambda)                            │
└───────────────────┬─────────────────────┬───────────────────────┘
                    │                     │
                    ▼                     ▼
    ┌───────────────────────┐   ┌───────────────────────┐
    │ Current Snapshots     │   │ Historical Analytics  │
    │ (processed/discovery/ │   │ (processed/forecast/  │
    │ catalog_latest/ +     │   │ analytics/ + DuckDB)  │
    │ processed/forecast/   │   │                       │
    │ latest/ on S3)        │   │                       │
    └───────────┬───────────┘   └───────────┬───────────┘
                │                           │
                └─────────────┬─────────────┘
                              │
                    ┌─────────┴─────────┐
                    │  Processor Layer  │
                    │ (raw -> processed)│
                    └─────────┬─────────┘
                              │
                    ┌─────────┴─────────┐
                    │    Raw Layer      │
                    │   (S3 raw/...)    │
                    └───────────────────┘
```

### Current Snapshot Layer (S3 Canonical Snapshots)

For low-latency current forecast and spot metadata queries:

**Why S3-first now:**
- Matches the current infrastructure direction
- Avoids introducing a serving database before storage semantics settle
- Keeps raw-to-processed lineage simple
- Works well for immutable per-scrape objects and mutable `latest/` snapshots

**Storage approach:**
- replaceable latest discovery catalog under `processed/discovery/catalog_latest/`
- immutable per-scrape canonical objects under `processed/forecast/canonical/`
- mutable latest snapshot per spot under `processed/forecast/latest/`
- API layer reads the discovery latest catalog for `/spots` metadata and forecast latest snapshots for current forecast endpoints

### Historical Data Layer (Parquet + DuckDB)

For analytical queries and historical access:

**Why Parquet on S3:**
- Cost-effective storage (~$0.023/GB/month)
- Columnar format optimized for analytical queries
- Works with DuckDB (fast, in-process), Athena (serverless), pandas
- Immutable data — perfect for long-term caching

**Partitioning strategy:**
```
s3://surf-alerts-data/processed/forecast/analytics/
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
| Current store | S3 latest snapshots | Discovery catalog + latest forecast objects |
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
raw/... (S3)
    │
    ├──▶ Discovery processors
    │      - Append discovery Parquet version tables
    │      - Rebuild processed/discovery/catalog_latest/
    │
    ├──▶ Canonical processor
    │      - Write immutable per-scrape forecast object
    │      - Refresh processed/forecast/latest/<spot_id>
    │
    └──▶ Analytics processor
           - Append Parquet to processed/forecast/analytics/
           - Partition by year/month/spot_id
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
│       │   └── discovery.py     # Spot catalog and regional search logic
│       ├── repositories/
│       │   ├── snapshots.py     # S3 latest snapshot reads
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
