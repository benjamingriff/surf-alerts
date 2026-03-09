# Data Layer Overview

> **Status: PLANNED** | Target architecture for the next storage/orchestration iteration

## Summary

The data platform is moving from a flat "scraper writes JSON to S3" model toward a **partial medallion** structure with one S3 bucket and three top-level prefixes:

- `raw/` - immutable, short-lived scraper outputs
- `processed/` - durable canonical and analytical data
- `control/` - manifests, checkpoints, and event bookkeeping

This keeps the design simple while making room for more event-driven orchestration and cleaner separation between source payloads and usable data products.

## Why This Change

The current docs describe two real but disconnected data stories:

1. Forecast data needs a normalized analytical model for time-series queries.
2. Spot discovery data behaves more like operational snapshots and change feeds.

Those are both valid, but they should live inside one storage architecture instead of being documented as separate patterns.

## Chosen Approach

| Component | Choice | Rationale |
|-----------|--------|-----------|
| Bucket layout | One S3 bucket with layered prefixes | Simple lifecycle management, simpler permissions, no cross-bucket orchestration |
| Landing layer | `raw/` | Immutable source payloads, replay/debug support, cheap expiry |
| Usable layer | `processed/` | Canonical, presentation, and historical forecast outputs plus discovery tables |
| Orchestration support | `control/` | Keeps manifests/checkpoints out of data prefixes |
| Event boundary | Raw object creation | Natural handoff from scraper to processor |

## Layer Model

### Raw

`raw/` stores near-source payloads written by scrapers:

- forecast scrape envelopes
- raw spot `/reports` responses
- sitemap snapshots

Raw data is append-only and short-lived. It exists to support replay, debugging, and downstream processing, not direct serving.

### Processed

`processed/` stores the usable outputs:

- append-only discovery version tables
- append-only discovery events
- derived latest discovery catalog snapshots
- canonical per-scrape forecast objects
- timezone-day presentation artifacts for notifications
- analytical forecast Parquet tables

This is the long-lived layer downstream code should consume.

### Control

`control/` stores manifests, processing records, and checkpoints that support event-driven orchestration without mixing operational metadata into business data prefixes.

## Domain View

### Discovery Domain

The discovery flow is centered on sitemap-driven lifecycle detection plus spot-report-driven metadata versioning:

- raw sitemap snapshots land in `raw/sitemap/`
- a discovery diff processor emits `added` and `removed` events
- raw spot reports land in `raw/spot_report/`
- a spot report processor computes checksums and appends new discovery versions when content changes
- a catalog builder materializes the latest live catalog from the append-only discovery tables

This uses logical SCD2 semantics without mutating Parquet rows in place. Current state is derived from the highest `version_ts` per `spot_id`.

### Forecast Domain

Forecast data should be documented as a full layered pipeline:

- raw per-spot forecast scrapes under `raw/forecast/`
- timezone-batch manifests and completion markers under `control/`
- canonical per-spot forecast objects under `processed/forecast/canonical/`
- timezone-day presentation outputs under `processed/forecast/presentation/`
- append-only historical Parquet under `processed/forecast/history/`

The existing forecast star schema remains the right historical model, but it now sits behind explicit batch orchestration and presentation layers.

## Naming And Retention

Storage keys should consistently use partition-like segments such as:

- `spot_id=<id>`
- `scrape_date=YYYY-MM-DD`
- `snapshot_date=YYYY-MM-DD`
- `year=YYYY`
- `month=MM`
- `run_id=<id>`

Retention should be short for `raw/` and long-lived for `processed/` and `control/`.

## Documentation

| Page | Contents |
|------|----------|
| [Storage Layout](storage-layout.md) | Top-level prefixes, directory conventions, retention, event contract |
| [Discovery Schema](discovery-schema.md) | Versioned Parquet tables for discovery history and latest catalog builds |
| [Discovery Transformations](discovery-transformations.md) | Checksum rules, event detection, and latest catalog materialization |
| [Forecast Pipeline](forecast-pipeline.md) | Timezone-batch orchestration, completion logic, canonical outputs, presentation, and history |
| [Forecast Schema](forecast-schema.md) | Historical forecast table definitions under `processed/forecast/history/` |
| [Forecast Transformations](forecast-transformations.md) | How completed forecast batches become canonical, presentation, and history outputs |
| [Forecast Queries](forecast-queries.md) | Example SQL against the forecast historical layer |
