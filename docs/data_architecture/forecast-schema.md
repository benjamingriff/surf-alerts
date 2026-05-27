# Forecast Schema

> **Status: IMPLEMENTED v1** | Last verified: 2026-05-27

Forecast v1 stores successful Surfline forecast scrapes directly in Supabase/Postgres fact tables. The migration is `db/migrations/0002_create_forecast_tables.sql`.

Only five active tables exist in v1:

- `forecast_fact_rating`
- `forecast_fact_wave`
- `forecast_fact_swells`
- `forecast_fact_wind`
- `forecast_fact_tides`

Weather and sunlight are intentionally not collected or stored in v1 because they are not surf-condition inputs for this project. There are no placeholder weather or sunlight tables.

## Common Lineage And Control Fields

Every forecast fact table includes:

| Column | Purpose |
|--------|---------|
| `forecast_run_id` | Deterministic Forecast Run identifier |
| `spot_id` | Surfline spot identifier |
| `spot_version_id` | Discovery version current when the spot was planned |
| `forecast_ts` | Forecast-valid timestamp from Surfline |
| `scraped_at` | Actual scrape timestamp |
| `scheduled_utc_time` | Intended EventBridge schedule tick |
| `utc_offset` | Stored integer UTC offset used for scheduling/debugging |
| `timezone` | Spot timezone from discovery state |
| `source_raw_key` | S3 raw object key used to produce the row |
| `schema_version` | Raw/transform schema version |
| `created_at` | Postgres insertion timestamp |

`spot_version_id` is lineage only and is intentionally excluded from unique constraints.

All tables have a `scraped_at` index for future manual or automated cleanup. v1 does not implement automatic Postgres retention.

## Idempotency

The Forecast Spot Processor inserts append-only rows with `ON CONFLICT DO NOTHING`. Unique constraints match the processor conflict targets:

| Table | Unique key |
|-------|------------|
| `forecast_fact_rating` | `forecast_run_id, spot_id, forecast_ts` |
| `forecast_fact_wave` | `forecast_run_id, spot_id, forecast_ts` |
| `forecast_fact_swells` | `forecast_run_id, spot_id, forecast_ts, swell_index` |
| `forecast_fact_wind` | `forecast_run_id, spot_id, forecast_ts` |
| `forecast_fact_tides` | `forecast_run_id, spot_id, forecast_ts, tide_index` |

`forecast_fact_swells.swell_index` preserves the original swell slot from the wave endpoint. `forecast_fact_tides.tide_index` preserves source tide ordering.

## Table-Specific Fields

### `forecast_fact_rating`

- `rating_key`
- `rating_value`
- `source_utc_offset`
- `run_init_ts`

### `forecast_fact_wave`

- `surf_min`
- `surf_max`
- `surf_plus`
- `surf_human_relation`
- `surf_raw_min`
- `surf_raw_max`
- `surf_optimal_score`
- `power`
- `probability`
- `source_utc_offset`
- `location_lon`, `location_lat`
- `forecast_location_lon`, `forecast_location_lat`
- `offshore_location_lon`, `offshore_location_lat`
- `run_init_ts`

### `forecast_fact_swells`

- `swell_index`
- `height`
- `period`
- `impact`
- `power`
- `direction`
- `direction_min`
- `optimal_score`

All source swell slots are retained, including zero-height/inactive swells.

### `forecast_fact_wind`

- `speed`
- `gust`
- `direction`
- `direction_type`
- `optimal_score`
- `source_utc_offset`
- `location_lon`, `location_lat`
- `run_init_ts`

### `forecast_fact_tides`

- `tide_index`
- `tide_type`
- `height`
- `source_utc_offset`
- `tide_location_name`
- `tide_location_lon`, `tide_location_lat`
- `tide_location_min`, `tide_location_max`, `tide_location_mean`

All tide entries are stored, including NORMAL, HIGH, and LOW entries. Tide heights are requested and stored in feet.

## Source Endpoints

v1 transforms only these raw payload keys:

- `rating`
- `tides`
- `wave`
- `wind`

Swells are derived from `wave.data.wave[].swells`. Weather and sunlight payloads, if present in legacy samples, are ignored by the v1 transform.
