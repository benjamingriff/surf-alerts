# Discovery Processors

> **Status: PLANNED** | Event-driven Lambdas for discovery versioning and catalog builds

The target discovery flow replaces the legacy spot reconciler with a set of smaller processors triggered by raw S3 writes and downstream manifests.

## Planned Packages

### `packages/jobs/discovery_diff`

Triggered after a new raw sitemap object lands.

Responsibilities:

- read `raw/sitemap/...`
- read the current live catalog from `processed/discovery/catalog_latest/dim_spots_core.parquet`
- compare sitemap `spot_id`s against the latest catalog
- append `added` and `removed` rows to `processed/discovery/events/...`
- enqueue new IDs for the spot scraper

### `packages/jobs/spot_report_processor`

Triggered after a new raw spot report object lands.

Responsibilities:

- read `raw/spot_report/...`
- canonicalize the spot object
- compute a checksum
- compare to the latest checksum for the `spot_id`
- append a `changed` event when the checksum differs
- append new version rows to discovery dimension tables

### `packages/jobs/catalog_builder`

Triggered after new discovery versions are written.

Responsibilities:

- read append-only discovery Parquet tables
- select the latest `version_ts` per `spot_id`
- filter out tombstone latest rows
- join child dimensions by `spot_version_id`
- write a fresh `processed/discovery/catalog_latest/` snapshot

## Trigger Model

Recommended trigger pattern:

- raw sitemap object created -> `discovery_diff`
- raw spot report object created -> `spot_report_processor`
- discovery version write completion or manifest -> `catalog_builder`

This keeps discovery processing event-driven while avoiding tight coupling between scrapers and transformation logic.

## Why Split The Processors

Compared to a single monolithic reconciler, this design:

- maps cleanly onto raw S3 event boundaries
- keeps each Lambda focused on one stage
- makes retries and replay easier
- separates lifecycle detection from rich metadata versioning
- supports periodic rescraping of live spots without re-running sitemap diffing

See [Discovery Transformations](../data_architecture/discovery-transformations.md) for the full lifecycle rules and [Data Flow](../architecture/data-flow.md) for the planned system flow.
