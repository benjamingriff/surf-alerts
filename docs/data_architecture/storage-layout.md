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
- there is no separate `gold` layer yet; API-ready snapshots and analytics live inside `processed`

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
    spot_id=<spot_id>/
      scrape_date=YYYY-MM-DD/
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

Durable canonical data for operational reads plus longer-lived analytical tables.

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
      spot_id=<spot_id>/
        scrape_date=YYYY-MM-DD/
          scrape_ts=<scrape_ts>/
            forecast.json.gz
    latest/
      spot_id=<spot_id>/
        forecast.json.gz
    analytics/
      fact_rating/year=YYYY/month=MM/...
      fact_wave/year=YYYY/month=MM/...
      fact_swells/year=YYYY/month=MM/...
      fact_wind/year=YYYY/month=MM/...
      fact_weather/year=YYYY/month=MM/...
      fact_tides/year=YYYY/month=MM/...
      dim_sunlight/year=YYYY/month=MM/...
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
    processing/
      domain=<domain>/
        date=YYYY-MM-DD/
          run_id=<run_id>.json
  checkpoints/
    discovery/
      latest.json
    forecast/
      latest.json
```

## Domain Mapping

### Forecast

- Scraper writes one raw forecast envelope to `raw/forecast/...`
- Processor normalizes that scrape into one canonical serving object at `processed/forecast/canonical/...`
- A latest mutable snapshot is maintained at `processed/forecast/latest/...`
- Historical Parquet remains under `processed/forecast/analytics/...`

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
- `event_date=YYYY-MM-DD`
- `year=YYYY`
- `month=MM`
- `run_id=<id>`

Rules:

- raw paths are append-only
- processed historical paths are append-only
- `processed/discovery/catalog_latest/` is replaceable derived state
- `processed/forecast/latest/` remains the mutable latest forecast view
- high-cardinality entities should be isolated by `spot_id=<id>` rather than embedded in filenames

## Object Metadata Requirements

All raw and processed payloads should carry:

- `schema_version`
- `run_id`
- `produced_at`
- `source_type`
- `spot_id` when applicable

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
  "key": "raw/forecast/spot_id=584204204e65fad6a77090d2/scrape_date=2026-03-08/run_id=abc123.json.gz",
  "spot_id": "584204204e65fad6a77090d2",
  "scraped_at": "2026-03-08T12:00:00Z",
  "schema_version": 1
}
```

Downstream processors should use the event payload plus the raw object contents to build `processed/` outputs.

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
- [Forecast Schema](forecast-schema.md) - analytical table definitions under `processed/forecast/analytics/`
- [Forecast Transformations](forecast-transformations.md) - how raw forecast payloads become analytical tables
- [Forecast Queries](forecast-queries.md) - query examples against the analytical layer
