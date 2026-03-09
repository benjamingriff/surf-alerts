# Forecast Transformations

> **Status: IMPLEMENTED** (analytics transform design) | Last verified: 2026-03-06

These transformations describe how raw forecast payloads become analytical Parquet tables under `processed/forecast/analytics/`.

For the broader layered storage design, see [Storage Layout](storage-layout.md).

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

## Partitioning Strategy

### Chosen Strategy: `year/month/spot_id`

```
s3://surf-alerts-data/processed/forecast/analytics/
  fact_rating/
    year=2026/
      month=01/
        spot_id=584204204e65fad6a77090d2/
          data_20260117.parquet
          data_20260118.parquet
```

### Rationale

| Query Pattern | Partition Pruning |
|---------------|-------------------|
| "Last week's forecasts for spot X" | Prunes by month + spot_id |
| "All spots on 2026-01-17" | Prunes by year/month |
| "Historical data for spot X" | Prunes by spot_id across all partitions |

### File Size Targets

- **Target:** 1-5 MB per Parquet file
- **Per scrape:** ~65 KB total (all tables combined)
- **Recommendation:** Aggregate multiple scrapes per file (daily or weekly)

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
