# Forecast Transformations

> **Status: PLANNED** | Batch-driven rules for canonical forecast outputs, presentation publishing, and historical writes

These transformations describe how completed forecast batches become:

- canonical per-spot forecast objects under `processed/forecast/canonical/`
- timezone-day presentation outputs under `processed/forecast/presentation/`
- append-only historical Parquet tables under `processed/forecast/history/`

For the batch/control model, see [Forecast Pipeline](forecast-pipeline.md). For the table definitions, see [Forecast Schema](forecast-schema.md).

## Source Roles

Forecast processing uses two upstream sources with distinct responsibilities:

- `raw/forecast/...`
  - stores one immutable source envelope per scraped `spot_id`
  - remains close to Surfline's source shape
- `control/manifests/processing/domain=forecast/...`
  - defines a complete timezone-local batch
  - is the authoritative trigger for downstream processing

Raw object creation alone should not trigger full forecast processing. Canonicalization and publication start only after batch completeness has been proven by the control layer.

## Processor Flow

### 1. Batch planner

Steps:

1. run hourly in UTC
2. read the live discovery catalog
3. group live spots by `timezone`
4. determine which timezone-local scrape times are due
5. write one batch manifest per due timezone-local day
6. enqueue one forecast scrape request per `spot_id`

### 2. Forecast scraper

Steps:

1. read one queued `spot_id` and batch context
2. call the six Surfline forecast endpoints
3. combine them into one raw forecast envelope
4. write one raw object to `raw/forecast/...`
5. write one completion marker under `control/completions/...`

### 3. Batch completion checker

Steps:

1. read the batch manifest
2. count the observed completion markers
3. compare `completed_spot_count` to `expected_spot_count`
4. when the counts match, write one processing manifest under `control/manifests/processing/domain=forecast/...`

### 4. Forecast processor

Steps:

1. read all raw forecast objects in the completed batch
2. validate that membership matches the batch manifest
3. canonicalize each raw payload into the stable forecast business model
4. write canonical outputs under `processed/forecast/canonical/...`
5. publish one timezone-day presentation artifact under `processed/forecast/presentation/...`
6. append rows to the historical Parquet tables under `processed/forecast/history/...`

## Canonicalization Rules

Before history rows or presentation outputs are written, each raw payload should be transformed into a canonical forecast object.

Canonicalization rules should be documented as:

1. Keep `spot_id`, `timezone`, `local_batch_date`, and `batch_id` with every canonical object.
2. Normalize forecast timestamps to explicit `forecast_valid_at` fields.
3. Preserve stable, semantically meaningful order where the source arrays rely on it, especially `swells`.
4. Normalize missing values consistently as `null`.
5. Record lineage with `source_run_id` and `source_raw_key`.
6. Keep the canonical model independent from Surfline's endpoint-specific nesting.

## Presentation Build Rules

The presentation layer should be published once per `timezone + local_batch_date`.

Processing rules:

1. read all canonical outputs in the completed batch
2. derive alert-oriented summary fields per `spot_id`
3. rank or filter spots according to the notification logic
4. write one timezone-day presentation artifact

Presentation outputs should be derived state, safe to rebuild, and explicitly tied to the completed batch that produced them.

## Handling Nested Structures

### The Swells Challenge

Each wave entry contains a `swells[]` array with 6 elements:

```json
"swells": [
  { "height": 0, "period": 0, ... },      // index 0 - inactive
  { "height": 3.4, "period": 10, ... },   // index 1 - active
  { "height": 2.7, "period": 15, ... },   // index 2 - active
  { "height": 0, "period": 0, ... },      // index 3 - inactive
  { "height": 0, "period": 0, ... },      // index 4 - inactive
  { "height": 0, "period": 0, ... }       // index 5 - inactive
]
```

### Options Considered

| Approach | Implementation | Pros | Cons |
|----------|----------------|------|------|
| **Separate table** (chosen) | `fact_swells` with swell_index | Filterable, aggregatable | Requires join |
| Flattened columns | 42 columns (6 * 7 fields) | No join needed | Sparse, hard to query "any swell with X" |
| JSON column | `swells JSON` in fact_wave | Simple schema | No columnar benefits, full scan required |

### Why Separate Table?

1. **Query flexibility**: Easily answer "find spots with period > 12s"
2. **Storage efficiency**: Filter out zero-height swells (reduces ~720 to ~240 rows)
3. **Aggregations**: Natural `AVG(period) WHERE impact > 0.3`
4. **Schema simplicity**: 7 columns vs 42 sparse columns

### Preserving swell_index

The `swell_index` column (0-5) preserves the original array position. This may be semantically meaningful (e.g., swells ordered by impact or direction group).

### Why Filter Zero-Height Swells?

Original data has 6 swells per wave entry, but typically only 1-3 are active:

```json
"swells": [
  { "height": 0, ... },   // inactive - FILTERED
  { "height": 3.4, ... }, // active - KEPT
  { "height": 2.7, ... }, // active - KEPT
  { "height": 0, ... },   // inactive - FILTERED
  { "height": 0, ... },   // inactive - FILTERED
  { "height": 0, ... }    // inactive - FILTERED
]
```

Filtering reduces `fact_swells` from ~720 to ~240 rows per scrape (~67% storage reduction).

---

## Historical Partitioning Strategy

### Chosen strategy: time-first Parquet

```
s3://surf-alerts-data/processed/forecast/history/
  fact_rating/
    year=2026/
      month=01/
        forecast_date=2026-01-17/
          part-000.parquet
          part-001.parquet
```

### Rationale

| Query Pattern | Partition Pruning |
|---------------|-------------------|
| "All spots on 2026-01-17" | Prunes by year/month/forecast_date |
| "Last week's forecasts for spot X" | Prunes by day partitions, then filters by `spot_id` |
| "Load a time window into a warehouse" | Reads contiguous time partitions without scanning spot-specific directories |

### File Size Targets

- **Target:** 1-5 MB per Parquet file
- **Per scrape:** ~65 KB total (all tables combined)
- **Recommendation:** Compact multiple spots into shared daily files; avoid one file per spot per scrape

---

## Design Justifications

### Why Star Schema Over Wide Table?

| Consideration | Star Schema | Wide Table |
|---------------|-------------|------------|
| **Row counts** | Vary naturally (120-384) | Would require NULL padding or duplication |
| **NULL values** | Minimal | 30%+ (misaligned timestamps) |
| **Swell columns** | 7 per row | 42 sparse columns |
| **Query flexibility** | Independent queries per type | Must scan all columns |
| **Schema evolution** | Add new fact table | Migrate entire table |
| **Storage** | Efficient | Bloated with NULLs |

### Why Parquet Over Database?

| Factor | Parquet on S3 | Database (DynamoDB/RDS) |
|--------|---------------|-------------------------|
| **Cost** | ~$0.023/GB/month (S3) | Higher (provisioned or per-request) |
| **Query tools** | DuckDB, Athena, pandas | Requires connections, drivers |
| **Infrastructure** | Already using S3 | New resources needed |
| **Batch analytics** | Excellent (columnar) | Moderate |
| **Real-time** | Good (DuckDB in Lambda) | Excellent |
| **Schema changes** | Easy (additive) | Migrations required |

---

## Join Strategy

Historical forecast rows should retain `spot_id` as a column in every table so they can join directly to discovery and spot-location data.

Recommended joins:

- historical forecast tables -> `processed/discovery/catalog_latest/...` for current operational metadata
- historical forecast tables -> discovery version tables when point-in-time joins are needed later

The forecast domain should not duplicate the spot-location source of truth beyond the forecast attributes already embedded in the historical tables.

## Storage Estimates

### Per Spot Per Scrape

| Table | Rows | Estimated Size (Parquet) |
|-------|------|--------------------------|
| fact_rating | 120 | ~5 KB |
| fact_wave | 120 | ~15 KB |
| fact_swells | ~240 | ~12 KB |
| fact_wind | 120 | ~8 KB |
| fact_weather | 384 | ~15 KB |
| fact_tides | 168 | ~8 KB |
| dim_sunlight | 16 | ~2 KB |
| **Total** | ~1,168 | **~65 KB** |

### At Scale

| Scale | Raw Size | Compressed (Parquet) | S3 Cost/Month |
|-------|----------|----------------------|---------------|
| 100 spots x 1 year | 2.4 GB | ~0.8-1.2 GB | ~$0.03 |
| 1,000 spots x 1 year | 24 GB | ~8-12 GB | ~$0.25 |
| ~5,000 spots x 1 year | 120 GB | ~40-60 GB | ~$1.25 |

### Comparison to Raw JSON

- Raw JSON per scrape: ~380 KB (gzipped: ~50-60 KB)
- Parquet per scrape: ~65 KB
- Parquet is slightly larger than gzipped JSON but offers columnar query benefits
