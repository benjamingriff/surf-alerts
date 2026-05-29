# Forecast Data Volume and Supabase Storage Problem

## Project overview

Surf Alerts collects Surfline forecast data for known surf spots. The current pipeline writes recent forecast facts into a transactional Supabase/Postgres database so the application has a simple hot store for operational queries, debugging, and near-term product use. A longer-term analytics/archive layer, likely Parquet-based object storage, is still to be designed.

## Current problem

The deployed forecast scraper is now collecting daily forecast data for roughly **9,000 Surfline spots**. Each successful spot scrape stores the full forecast horizon into five Postgres fact tables:

- `forecast_fact_rating`
- `forecast_fact_wave`
- `forecast_fact_swells`
- `forecast_fact_wind`
- `forecast_fact_tides`

This is too much data for a free Supabase database if retained directly in Postgres.

## Observed sample data

Current table sizes observed in Supabase:

| Table | Rows | Size |
|---|---:|---:|
| `forecast_fact_rating` | 19,080 | 13 MB |
| `forecast_fact_swells` | 113,406 | 81 MB |
| `forecast_fact_tides` | 23,380 | 19 MB |
| `forecast_fact_wave` | 19,200 | 15 MB |
| `forecast_fact_wind` | 18,960 | 14 MB |
| **Total** | **194,026** | **142 MB** |

This implies approximately **0.89 MB per spot per daily scrape** based on the current sample.

## Estimated daily volume

For a full daily run across **9,000 spots**:

- Estimated rows per spot per day: **~1,200–1,300 rows**
- Estimated total rows per day: **~11M–11.5M rows**
- Estimated Postgres storage per day from observed data: **~8 GB/day**
- Safer planning estimate including index/table bloat: **~8–10 GB/day**

Expected table split per full day:

| Table | Estimated rows/day |
|---|---:|
| `forecast_fact_rating` | ~1.08M |
| `forecast_fact_wave` | ~1.08M |
| `forecast_fact_wind` | ~1.08M |
| `forecast_fact_swells` | ~6.48M |
| `forecast_fact_tides` | ~1.3M–1.6M |
| **Total** | **~11M–11.5M** |

## Estimated retained database size

For 9,000 spots scraped daily:

| Retention | Estimated size |
|---:|---:|
| 1 full day | ~8–10 GB |
| 2 full days | ~16–20 GB |
| 3 full days | ~24–30 GB |
| 5 full days | ~40–50 GB |
| 7 full days | ~56–70 GB |

## Compute and database pressure

The issue is not only storage. Daily ingestion also requires Supabase/Postgres to handle:

- ~11M+ inserted rows per day
- five fact-table insert streams
- unique constraint checks for idempotency
- secondary index maintenance on each table
- transaction overhead per spot/run
- vacuum/autovacuum pressure as old data is deleted

At this scale, a free Supabase database is not an appropriate long-term hot store for all forecast facts.

## Likely failure mode

If the database reaches its storage limit, Postgres writes are expected to fail. The pipeline should mark these as processing failures with source `postgres`, while AWS infrastructure may continue scraping, writing raw S3 objects, sending SQS messages, and consuming Lambda/DynamoDB/S3/CloudWatch resources unless the scheduler and workers are disabled.

## Implication

The current full-scale forecast ingestion should not continue writing all daily forecast facts into the free Supabase database without a retention/offload strategy.

A likely target design is:

- keep Supabase/Postgres as a short-retention hot transactional store;
- archive completed daily forecast data to Parquet/object storage;
- delete or partition-drop old Postgres data after successful archive;
- retain only a small hot window, likely **1–3 days** on a constrained Supabase plan, or **7–14 days** only on a larger paid database.
