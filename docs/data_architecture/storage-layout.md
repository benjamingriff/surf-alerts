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
3. **Mutable latest views only in processed** - only `processed/.../latest/` may be overwritten.
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
  taxonomy/
    scrape_date=YYYY-MM-DD/
      run_id=<run_id>.json.gz
```

Retention defaults:

- `raw/forecast/`: 14 days
- `raw/spot_report/`: 30 days
- `raw/sitemap/`: 30 days
- `raw/taxonomy/`: 30 days

### `processed/`

Durable canonical data for operational reads plus longer-lived analytical tables.

```text
processed/
  discovery/
    snapshots/
      snapshot_date=YYYY-MM-DD/
        catalog.json.gz
    changes/
      change_date=YYYY-MM-DD/
        run_id=<run_id>.json.gz
    spots/
      spot_id=<spot_id>/
        latest.json.gz
    latest/
      catalog.json.gz
      state.json.gz

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

- Sitemap and taxonomy scrapers write to `raw/sitemap/...` and `raw/taxonomy/...`
- Reconciliation produces:
  - point-in-time catalog snapshots
  - append-only change files
  - a mutable latest catalog/state view
- Spot report scrapes write raw `/reports` payloads to `raw/spot_report/...`
- Downstream processors publish canonical spot records to `processed/discovery/spots/...`

## Key Conventions

Use partition-like path segments consistently:

- `spot_id=<id>`
- `scrape_date=YYYY-MM-DD`
- `snapshot_date=YYYY-MM-DD`
- `change_date=YYYY-MM-DD`
- `year=YYYY`
- `month=MM`
- `run_id=<id>`

Rules:

- raw paths are append-only
- processed historical paths are append-only
- only `processed/.../latest/` is mutable
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

## Relationship To Existing Forecast Docs

The existing forecast star schema remains valid, but it now sits inside the broader storage model:

- [Data Layer Overview](README.md) - overall storage architecture
- [Forecast Schema](forecast-schema.md) - analytical table definitions under `processed/forecast/analytics/`
- [Forecast Transformations](forecast-transformations.md) - how raw forecast payloads become analytical tables
- [Forecast Queries](forecast-queries.md) - query examples against the analytical layer
