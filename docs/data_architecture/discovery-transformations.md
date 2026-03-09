# Discovery Transformations

> **Status: PLANNED** | Change detection and version-building rules for discovery data

These transformations describe how raw sitemap and spot-report payloads become versioned Parquet tables under `processed/discovery/`.

For the table definitions, see [Discovery Schema](discovery-schema.md). For bucket layout, see [Storage Layout](storage-layout.md).

## Source Roles

Discovery uses two upstream sources with different responsibilities:

- `raw/sitemap/...`
  - defines the current universe of Surfline spot IDs
  - primarily drives `added` and `removed` events
- `raw/spot_report/...`
  - defines the rich metadata for a single spot
  - primarily drives `changed` events via checksum comparison

Taxonomy is not part of the active target discovery flow.

## Canonical Spot Object

Before hashing or writing any dimension rows, the spot report payload should be transformed into a canonical in-memory object.

Canonicalization rules should be documented as:

1. Use stable field names and stable nesting.
2. Sort object keys before serialization.
3. Preserve semantically meaningful array order:
   - breadcrumbs
   - cameras
   - ability levels
   - board types
4. Normalize missing values consistently as `null`.
5. Remove volatile fields that should not create new versions unless they are intentionally part of the model.

The checksum must be computed from this canonical object, not from the raw JSON string.

## Event Detection Rules

### Added

Triggered when a sitemap run contains a `spot_id` that does not exist in the latest catalog.

Writes:

- `discovery_events` row with `event_type='added'`
- new `dim_spots_core` version row after the spot report is processed
- new child dimension rows for the created `spot_version_id`

### Removed

Triggered when a `spot_id` exists in the latest catalog but is absent from the new sitemap run.

Writes:

- `discovery_events` row with `event_type='removed'`
- tombstone `dim_spots_core` row with a new `spot_version_id`
- no new child dimension rows

This preserves history without mutating older Parquet rows.

### Changed

Triggered when a refreshed spot report for an existing live spot produces a different canonical checksum than the latest known checksum for that `spot_id`.

Writes:

- `discovery_events` row with `event_type='changed'`
- new `dim_spots_core` version row
- new child dimension rows for the new `spot_version_id`

No event should be written if the checksum is identical.

## Processor Flow

### 1. Discovery Diff

Triggered from raw sitemap ingest.

Steps:

1. Read the new sitemap snapshot from `raw/sitemap/...`
2. Read the current latest catalog from `processed/discovery/catalog_latest/dim_spots_core.parquet`
3. Compare the set of sitemap `spot_id`s against the current catalog
4. Append `added` and `removed` rows to `processed/discovery/events/...`
5. Queue all `added` IDs for spot-report scraping

### 2. Spot Report Processor

Triggered from raw spot report ingest.

Steps:

1. Read the raw `/reports` payload from `raw/spot_report/...`
2. Canonicalize the spot object
3. Compute `content_checksum`
4. Read the latest core version for the `spot_id`
5. If the checksum changed:
   - append a `changed` event
   - append a new row to `dim_spots_core`
   - append rows to every child dimension table
6. If the checksum did not change:
   - do not write a new version

### 3. Catalog Builder

Triggered after new discovery version rows are written.

Steps:

1. Read append-only discovery version tables
2. Select the latest `version_ts` per `spot_id` from `dim_spots_core`
3. Filter out latest rows with `event_type='removed'`
4. Join child tables on `spot_version_id`
5. Write a fresh serving snapshot to `processed/discovery/catalog_latest/`

## Partitioning Strategy

### Version Tables

Use time-based partitions:

```text
processed/discovery/dim_spots_core/year=YYYY/month=MM/part-*.parquet
processed/discovery/dim_spot_location/year=YYYY/month=MM/part-*.parquet
...
```

This keeps appends simple and avoids rewriting large spot-specific partitions.

### Event Table

Use date partitions for lifecycle events:

```text
processed/discovery/events/year=YYYY/month=MM/event_date=YYYY-MM-DD/part-*.parquet
```

### Latest Snapshot

Treat `catalog_latest/` as replaceable derived state:

```text
processed/discovery/catalog_latest/dim_spots_core.parquet
processed/discovery/catalog_latest/dim_spot_location.parquet
...
```

## Compression

Recommended defaults:

- raw discovery JSON: `gzip`
- processed discovery Parquet: `snappy`

`snappy` is the right default for Parquet here because:

- it gives good size reduction without slowing reads significantly
- it is widely supported by DuckDB, Athena, Spark, and pandas
- it reduces S3 transfer bytes while keeping decompression cheap

`gzip` should stay on raw JSON because raw objects are retained for replay/debugging rather than analytical scans.

## Maintenance Refreshes

The sitemap-driven flow is not the only source of discovery changes.

A periodic maintenance job should be documented as a valid pattern:

- read the live catalog from `catalog_latest/`
- enqueue all live `spot_id`s for spot-report scraping
- allow checksum comparison to emit `changed` events only when content has actually changed

This is the expected source of most rich metadata changes such as:

- breadcrumb updates
- camera changes
- travel detail edits
- name or subregion changes
