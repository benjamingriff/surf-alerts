# Storage Layout

> **Status: PLANNED** | Target architecture for the next storage/orchestration iteration

## Overview

The data platform will use a **single S3 bucket** with three top-level prefixes:

- `raw/` - short-lived immutable scraper outputs
- `processed/` - durable canonical and analytical data
- `control/` - manifests, checkpoints, and event bookkeeping

This is a **partial medallion** design:

- `raw` is the landing zone for near-source payloads
- `processed` is the usable data layer
- there is no separate `gold` layer yet; canonical, presentation, and historical outputs live inside `processed`

## Design Principles

1. **One bucket, clear layers** - keep lifecycle and permissions simple with top-level prefixes.
2. **Immutable raw data** - every raw object is append-only and keyed by `run_id`.
3. **Mutable serving snapshots only in processed** - only derived serving artifacts may be overwritten.
4. **Lineage everywhere** - processed objects must record the raw key or keys they came from.
5. **Event boundary at raw ingest** - downstream jobs react to raw object creation rather than scraper-specific schedules.

## Top-Level Prefixes

```text
{bucket}/
  raw/
  processed/
  control/
```

### `raw/`

Immutable scraper outputs, stored close to source shape and retained briefly for replay/debugging.

```text
raw/
  forecast/
    timezone=<tz>/
      local_date=YYYY-MM-DD/
        batch_id=<batch_id>/
          spot_id=<spot_id>/
            run_id=<run_id>.json.gz
  spot_report/
    spot_id=<spot_id>/
      scrape_date=YYYY-MM-DD/
        run_id=<run_id>.json.gz
  sitemap/
    scrape_date=YYYY-MM-DD/
      run_id=<run_id>.json.gz
```

Retention defaults:

- `raw/forecast/`: 14 days
- `raw/spot_report/`: 30 days
- `raw/sitemap/`: 30 days

`raw/taxonomy/` is not part of the active target discovery flow. If retained for experiments or legacy backfills, it should follow the same short-retention pattern.

### `processed/`

Durable canonical data for operational reads, notification presentation, and longer-lived historical tables.

```text
processed/
  discovery/
    events/
      year=YYYY/
        month=MM/
          event_date=YYYY-MM-DD/
            part-*.parquet
    dim_spots_core/
      year=YYYY/
        month=MM/
          part-*.parquet
    dim_spot_location/
      year=YYYY/
        month=MM/
          part-*.parquet
    dim_spot_breadcrumbs/
      year=YYYY/
        month=MM/
          part-*.parquet
    dim_spot_cameras/
      year=YYYY/
        month=MM/
          part-*.parquet
    dim_spot_ability_levels/
      year=YYYY/
        month=MM/
          part-*.parquet
    dim_spot_board_types/
      year=YYYY/
        month=MM/
          part-*.parquet
    dim_spot_travel_details/
      year=YYYY/
        month=MM/
          part-*.parquet
    catalog_latest/
      dim_spots_core.parquet
      dim_spot_location.parquet
      dim_spot_breadcrumbs.parquet
      dim_spot_cameras.parquet
      dim_spot_ability_levels.parquet
      dim_spot_board_types.parquet
      dim_spot_travel_details.parquet

  forecast/
    canonical/
      timezone=<tz>/
        local_date=YYYY-MM-DD/
          batch_id=<batch_id>/
            spot_id=<spot_id>/
              forecast.json.gz
    presentation/
      timezone=<tz>/
        local_date=YYYY-MM-DD/
          forecast_summary.parquet
    history/
      fact_rating/year=YYYY/month=MM/forecast_date=YYYY-MM-DD/...
      fact_wave/year=YYYY/month=MM/forecast_date=YYYY-MM-DD/...
      fact_swells/year=YYYY/month=MM/forecast_date=YYYY-MM-DD/...
      fact_wind/year=YYYY/month=MM/forecast_date=YYYY-MM-DD/...
      fact_weather/year=YYYY/month=MM/forecast_date=YYYY-MM-DD/...
      fact_tides/year=YYYY/month=MM/forecast_date=YYYY-MM-DD/...
      dim_sunlight/year=YYYY/month=MM/forecast_date=YYYY-MM-DD/...
```

### `control/`

Operational metadata needed to support event-driven orchestration and replay.

```text
control/
  manifests/
    raw_ingest/
      source_type=<source_type>/
        date=YYYY-MM-DD/
          run_id=<run_id>.json
    forecast_batches/
      timezone=<tz>/
        local_date=YYYY-MM-DD/
          batch_id=<batch_id>.json
    processing/
      domain=<domain>/
        date=YYYY-MM-DD/
          run_id=<run_id>.json
      domain=forecast/
        timezone=<tz>/
          local_date=YYYY-MM-DD/
            batch_id=<batch_id>.json
  completions/
    forecast_batches/
      timezone=<tz>/
        local_date=YYYY-MM-DD/
          batch_id=<batch_id>/
            spot_id=<spot_id>.json
  checkpoints/
    discovery/
      latest.json
    forecast/
      latest_batch_by_timezone/
        timezone=<tz>.json
```

## Domain Mapping

### Forecast

- An hourly scheduler determines which timezone-local batches are due
- A batch manifest records the expected `spot_id` membership for one `timezone + local_date + scheduled_local_time`
- The scraper writes one raw forecast envelope per spot to `raw/forecast/...`
- Each successful scrape writes a completion marker under `control/completions/...`
- A forecast processor reads the completed batch and writes:
  - canonical per-spot outputs under `processed/forecast/canonical/...`
  - one daily timezone-day presentation artifact under `processed/forecast/presentation/...`
  - append-only historical Parquet under `processed/forecast/history/...`

### Spot Discovery

- Sitemap scrapes write raw snapshots to `raw/sitemap/...`
- A `discovery_diff` processor compares sitemap IDs against the current catalog and appends `added` and `removed` rows to `processed/discovery/events/...`
- Spot report scrapes write raw `/reports` payloads to `raw/spot_report/...`
- A `spot_report_processor` canonicalizes the payload, computes a checksum, and appends new version rows to the discovery dimension tables when content changes
- A `catalog_builder` writes a replaceable serving snapshot to `processed/discovery/catalog_latest/`

The version tables are the source of truth. `catalog_latest/` is a derived operational snapshot for fast reads.

## Key Conventions

Use partition-like path segments consistently:

- `spot_id=<id>`
- `scrape_date=YYYY-MM-DD`
- `local_date=YYYY-MM-DD`
- `forecast_date=YYYY-MM-DD`
- `event_date=YYYY-MM-DD`
- `year=YYYY`
- `month=MM`
- `run_id=<id>`
- `batch_id=<id>`

Rules:

- raw paths are append-only
- processed historical paths are append-only
- `processed/discovery/catalog_latest/` is replaceable derived state
- `processed/forecast/presentation/` is replaceable derived state at timezone-day granularity
- high-cardinality entities should stay as columns unless they materially improve pruning without creating tiny-file layouts

## Object Metadata Requirements

All raw and processed payloads should carry:

- `schema_version`
- `run_id`
- `produced_at`
- `source_type`
- `spot_id` when applicable
- `batch_id` when batch-scoped
- `timezone` and `local_batch_date` for forecast batch outputs

Processed payloads should additionally carry:

- `source_keys`
- `processed_at`
- `processor_version`

## Event Contract

Raw object creation is the orchestration boundary.

```json
{
  "event_type": "raw_ingested",
  "source_type": "forecast",
  "run_id": "uuid-or-stable-id",
  "bucket": "surf-alerts-data",
  "key": "raw/forecast/timezone=Europe-London/local_date=2026-03-08/batch_id=lon-2026-03-08-0700/spot_id=584204204e65fad6a77090d2/run_id=abc123.json.gz",
  "spot_id": "584204204e65fad6a77090d2",
  "batch_id": "lon-2026-03-08-0700",
  "timezone": "Europe/London",
  "local_batch_date": "2026-03-08",
  "scraped_at": "2026-03-08T12:00:00Z",
  "schema_version": 1
}
```

Forecast downstream processors should use the event payload plus the raw object contents to update completion markers. Batch-level canonicalization should start from the processing manifest, not from any single raw object alone.

## Compression

Recommended defaults:

- raw JSON objects: `gzip`
- processed Parquet tables: `snappy`

`snappy` is the preferred Parquet codec because it provides strong read performance with good compression and broad engine support.

## Relationship To Existing Forecast Docs

The existing forecast star schema remains valid, but it now sits inside the broader storage model:

- [Data Layer Overview](README.md) - overall storage architecture
- [Discovery Schema](discovery-schema.md) - discovery version tables and latest catalog shape
- [Discovery Transformations](discovery-transformations.md) - checksum rules and event-driven discovery flow
- [Forecast Pipeline](forecast-pipeline.md) - timezone-batch orchestration, completion markers, and forecast layer responsibilities
- [Forecast Schema](forecast-schema.md) - historical table definitions under `processed/forecast/history/`
- [Forecast Transformations](forecast-transformations.md) - how completed forecast batches become canonical, presentation, and history outputs
- [Forecast Queries](forecast-queries.md) - query examples against the historical layer
