# Migration Plan

> **Status: PLANNED** | Not yet started

Migrate 1TB+ of legacy forecast JSON data to the new Parquet archive format.

| Metric | Value |
|--------|-------|
| **Estimated Total Cost** | ~$6-8 |
| **Estimated Duration** | 3-5 days (automated) |
| **Compute** | EC2 Spot instance (r6i.large) |
| **Region** | us-west-2 |

---

## Current vs Target Structure

| Aspect | Current | Target |
|--------|---------|--------|
| **Source bucket** | `scraped-forecast-data` (us-west-2) | - |
| **Target bucket** | - | `surf-alerts-data` (us-west-2) |
| **Path** | `{date}/{spot_id}/{endpoint}.json` | See below |
| **Files per scrape** | 6 separate files | Consolidated monthly Parquet |
| **Format** | Uncompressed JSON | Parquet (snappy compressed) |

**Source structure:**
```
s3://scraped-forecast-data/
  2024-01-15/
    584204204e65fad6a770954d/
      rating.json
      sunlight.json
      tides.json
      wave.json
      weather.json
      wind.json
    584204204e65fad6a770954e/
      ...
```

**Target structure (archive tier only):**
```
s3://surf-alerts-data/forecasts/archive/
  year=2024/month=01/
    fact_wave.parquet      # ALL spots for month, sorted by spot_id
    fact_rating.parquet
    fact_wind.parquet
    fact_weather.parquet
    fact_tides.parquet
    fact_swells.parquet
    dim_sunlight.parquet
```

**Scrape timestamp**: Derived from date folder as `{date}T00:00:00Z` (known limitation — original scrape times not preserved for legacy data).

**Important:** Tide heights should be stored in feet and `rating_value` should use `FLOAT64` type — see [Forecast Schema](../data_architecture/forecast-schema.md) for details.

---

## S3 Inventory Setup

S3 Inventory provides a cost-effective way to enumerate all objects in a bucket. Instead of making thousands of LIST API calls, you get a pre-built manifest file delivered daily.

### Step 1: Enable S3 Inventory via AWS Console

1. Go to **S3** in the AWS Console
2. Select the **`scraped-forecast-data`** bucket
3. Go to the **Management** tab
4. Scroll to **Inventory configurations** and click **Create inventory configuration**

### Step 2: Configure the Inventory

| Setting | Value |
|---------|-------|
| **Inventory configuration name** | `migration-inventory` |
| **Inventory scope** | All objects in bucket (no prefix filter) |
| **Destination bucket** | Same bucket (`scraped-forecast-data`) |
| **Destination prefix** | `inventory/` |
| **Frequency** | Daily |
| **Output format** | Apache Parquet (more efficient than CSV) |
| **Status** | Enabled |

### Step 3: Select Additional Fields

Enable these optional fields:
- [x] Size
- [x] Last modified date
- [ ] Storage class (not needed)
- [ ] ETag (not needed)
- [ ] Encryption status (not needed)

### Step 4: Wait for Delivery

- First inventory report is delivered within **24-48 hours**
- Reports are delivered to: `s3://scraped-forecast-data/inventory/scraped-forecast-data/migration-inventory/`
- The manifest file is at: `.../manifest.json`

### Step 5: Reading the Inventory

The inventory manifest points to one or more Parquet data files:

```python
import boto3
import json
import pyarrow.parquet as pq

s3 = boto3.client('s3')

# 1. Read manifest
manifest_key = "inventory/scraped-forecast-data/migration-inventory/2026-01-20T00-00Z/manifest.json"
manifest = json.loads(s3.get_object(Bucket='scraped-forecast-data', Key=manifest_key)['Body'].read())

# 2. Read data files listed in manifest
for file_info in manifest['files']:
    key = file_info['key']
    # Read Parquet directly from S3
    table = pq.read_table(f"s3://scraped-forecast-data/{key}")

    for row in table.to_pydict():
        bucket = row['bucket']
        key = row['key']
        size = row['size']
        last_modified = row['last_modified_date']
        # Process...
```

### Step 6: Disable After Migration

Once migration is complete:
1. Go to **S3 > scraped-forecast-data > Management > Inventory configurations**
2. Select `migration-inventory` and click **Delete**
3. Optionally delete the `inventory/` prefix in the bucket

### Cost

- **Inventory cost**: $0.0025 per million objects listed
- For 10 million files: **$0.025** (essentially free)

---

## Cost Breakdown

| Category | Estimate |
|----------|----------|
| S3 Inventory | $0.03 |
| S3 GET (10M source files @ $0.0004/1000) | $4.00 |
| S3 PUT (archive: ~250 Parquet files) | $0.01 |
| EC2 Spot r6i.large (72-120 hrs @ $0.02/hr) | $1.50-2.50 |
| Data transfer | $0 (same region) |
| **Total** | **~$6-8** |

### Why EC2 Spot (Not Glue/Lambda)

| Option | Est. Cost | Pros | Cons |
|--------|-----------|------|------|
| **EC2 Spot** | **$1.50-3** | Cheapest, simple Python, runs for days | Spot interruption handling |
| Fargate Spot | $3-5 | Easier setup | Slightly more expensive |
| Glue | $9-20 | Managed Spark | 5-10x more expensive |
| Lambda | $15-30+ | Serverless | 15min timeout, complex orchestration |

---

## Implementation Plan

### Phase 0: Setup (Day 1)

1. **Enable S3 Inventory** on `scraped-forecast-data` bucket (see above)
   - Wait 24-48h for first manifest delivery

2. **Create migration package**:
   ```
   packages/migrations/forecast_data_migration/
   ├── pyproject.toml
   ├── src/forecast_data_migration/
   │   ├── __init__.py
   │   ├── main.py           # Entry point
   │   ├── inventory.py      # Parse S3 Inventory manifest
   │   ├── checkpoint.py     # Progress tracking for resume
   │   ├── transform.py      # JSON → Parquet (7 tables)
   │   ├── schemas.py        # PyArrow schemas
   │   └── io.py             # S3 read/write utilities
   ```

3. **Provision EC2 Spot instance** (us-west-2)
   - Instance: `r6i.large` (2 vCPU, 16GB RAM)
   - Spot price: ~$0.02/hr (vs $0.126 on-demand)
   - AMI: Amazon Linux 2023
   - IAM role: S3 read on `scraped-forecast-data`, read/write on `surf-alerts-data`

### Phase 1: Process by Month (Days 3-5)

**For each month (oldest to newest):**

1. Parse S3 Inventory to find all files for that month
2. Group by date -> spot_id -> endpoint
3. For each spot-day:
   - GET all 6 endpoint JSON files (handle missing gracefully)
   - Transform to PyArrow record batches
   - Accumulate in memory (sorted by spot_id)
4. Write 7 Parquet files for the month
5. Update checkpoint, move to next month

**Processing flow:**
```python
for year_month in sorted(all_months):  # "2023-01", "2023-02", ...
    # Accumulators for each table
    wave_batches, rating_batches = [], []
    # ... other tables

    for date in dates_in_month(year_month):
        for spot_id in spots_on_date(date):
            # Read 6 JSON files (or fewer if partial)
            data = read_all_endpoints(date, spot_id)
            scrape_ts = f"{date}T00:00:00Z"

            # Transform to batches
            wave_batches.append(transform_wave(data, spot_id, scrape_ts))
            rating_batches.append(transform_rating(data, spot_id, scrape_ts))
            # ... other tables

    # Sort by spot_id and write
    write_monthly_parquet(year_month, wave_batches, "fact_wave")
    write_monthly_parquet(year_month, rating_batches, "fact_rating")
    # ... other tables

    checkpoint.mark_month_complete(year_month)
```

**Memory management:**
- Process one month at a time
- ~10K spots x 30 days x ~1KB per spot-day = ~300MB per table in memory
- 16GB RAM handles this comfortably

### Phase 2: Validation (Day 5-6)

1. **Count validation**:
   - Source: Count unique (date, spot_id) pairs in inventory
   - Target: Sum row counts in all monthly Parquet files

2. **Sample validation**:
   - Pick 100 random source files
   - Re-transform and compare with Parquet values

3. **Schema validation**:
   - Query each Parquet file with DuckDB
   - Verify column types match [Forecast Schema](../data_architecture/forecast-schema.md)

### Phase 3: Cleanup (Day 7+)

1. Disable S3 Inventory on source bucket
2. Delete inventory manifest files
3. Keep source bucket for 30-day grace period, then delete
4. Archive migration checkpoints

---

## Checkpoint & Resume

**Checkpoint file** (saved to S3 every 5 minutes):
```json
{
  "migration_id": "2026-01-19-001",
  "completed_months": ["2023-01", "2023-02", "2023-03"],
  "current_month": "2023-04",
  "last_checkpoint": "2026-01-20T14:30:00Z",
  "stats": {
    "total_scrapes_processed": 547000,
    "partial_scrapes": 1234,
    "errors": []
  }
}
```

**Spot interruption handling:**
- Register SIGTERM handler (2-min warning from AWS)
- Save checkpoint immediately on signal
- On restart, skip completed months, resume current month from beginning

```python
import signal
import sys

def handle_spot_interruption(signum, frame):
    """Handle EC2 Spot interruption notice."""
    logger.warning("Spot interruption received, saving checkpoint...")
    checkpoint_manager.save(force=True)
    sys.exit(0)

# Register handler for SIGTERM (sent by AWS on Spot interruption)
signal.signal(signal.SIGTERM, handle_spot_interruption)
```

---

## Handling Edge Cases

| Scenario | Handling |
|----------|----------|
| **Missing endpoints** (1-5 of 6 files) | Include available data, NULL for missing columns |
| **Corrupt JSON** | Log error, skip that spot-day, continue |
| **Empty files** | Treat as missing |
| **Spot interruption** | Resume from last completed month |

---

## Parquet Transformations

Per the [Forecast Schema](../data_architecture/forecast-schema.md), transform each endpoint JSON to rows:

| Table | Rows per scrape | Key transformations |
|-------|-----------------|---------------------|
| `fact_wave` | 120 | Flatten `surf.*`, `surf.raw.*`, `associated.*` |
| `fact_swells` | ~240 | Explode `swells[]`, filter `height > 0` |
| `fact_rating` | 120 | Flatten `rating.rating.key/value` |
| `fact_wind` | 120 | Direct mapping |
| `fact_weather` | 384 | Direct mapping |
| `fact_tides` | 168 | Include `tideLocation.*` |
| `dim_sunlight` | 16 | Derive `date` from midnight timestamp |

**Critical**: Files MUST be sorted by `spot_id` for predicate pushdown to work.

---

## Files to Create

| File | Purpose |
|------|---------|
| `packages/migrations/forecast_data_migration/pyproject.toml` | Dependencies: boto3, pyarrow, pandas |
| `.../src/forecast_data_migration/__init__.py` | Package init |
| `.../src/forecast_data_migration/main.py` | CLI entry point |
| `.../src/forecast_data_migration/inventory.py` | Parse S3 Inventory Parquet manifest |
| `.../src/forecast_data_migration/checkpoint.py` | Save/load progress to S3 |
| `.../src/forecast_data_migration/transform.py` | All 7 table transformations |
| `.../src/forecast_data_migration/io.py` | S3 get_json, write_parquet helpers |
| `.../src/forecast_data_migration/schemas.py` | PyArrow schemas for each table |

---

## Verification Steps

After migration completes:

1. **Query with DuckDB** to verify data is readable:
   ```sql
   SELECT COUNT(*), MIN(forecast_ts), MAX(forecast_ts)
   FROM read_parquet('s3://surf-alerts-data/forecasts/archive/year=2023/month=01/fact_wave.parquet');
   ```

2. **Spot-check** 5 random spot-days against original JSON

3. **Verify row counts** match expected (~1,168 rows per scrape):
   - fact_wave: 120
   - fact_swells: ~240 (after filtering zero-height)
   - fact_rating: 120
   - fact_wind: 120
   - fact_weather: 384
   - fact_tides: 168
   - dim_sunlight: 16
