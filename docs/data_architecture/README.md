# Data Layer Overview

> **Status: IMPLEMENTED** | Last verified: 2026-03-06

## Problem Statement

The forecast scraper produces deeply nested JSON files from 6 Surfline API endpoints. These files are excellent for storage but difficult to query efficiently. We need to:

1. Flatten nested structures into queryable columns
2. Handle arrays (especially the `swells[]` array with 6 elements per wave entry)
3. Support time-series queries across forecast types
4. Enable joins between different forecast types (wave + wind + rating)
5. Keep storage efficient with columnar compression

## Solution Summary

**Approach:** Hybrid star schema with Parquet storage

| Component | Choice | Rationale |
|-----------|--------|-----------|
| Storage Format | Parquet on S3 | Columnar compression, works with DuckDB/Athena/pandas |
| Schema Style | Star schema (7 fact tables) | Different cardinalities per forecast type (16-384 rows) |
| Swells Handling | Separate `fact_swells` table | Enables flexible swell queries without 42 sparse columns |
| Partitioning | `year/month/spot_id` | Optimizes time-range + spot filtering |

## Original Data Structure

Each scrape produces two files per spot:

### metadata.json

```json
{
  "spot_id": "584204204e65fad6a77090d2",
  "timestamp": "2026-01-17T14:43:39.398066",
  "scraper": "forecast"
}
```

### data.json

Contains 6 top-level forecast types: `rating`, `sunlight`, `tides`, `wave`, `weather`, `wind`.

Each forecast type has this structure:

```json
{
  "associated": { /* metadata: location, units, timestamps */ },
  "data": { /* array(s) of forecast values */ },
  "permissions": { /* API permission info */ }
}
```

See [Forecast Schema](forecast-schema.md) for the full target schema, [Forecast Transformations](forecast-transformations.md) for how nested structures are handled, and [Forecast Queries](forecast-queries.md) for example SQL.

## Documentation

| Page | Contents |
|------|----------|
| [Forecast Schema](forecast-schema.md) | Star schema diagram, all table definitions, field mappings |
| [Forecast Transformations](forecast-transformations.md) | Nested structure handling, partitioning, storage estimates |
| [Forecast Queries](forecast-queries.md) | Example queries and data reconstruction |
