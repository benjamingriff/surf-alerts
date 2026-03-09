# Forecast Pipeline

> **Status: PLANNED** | Target orchestration and storage model for forecast ingestion, canonicalization, presentation, and history

This page defines the forecast pipeline end to end:

- hourly scheduling
- timezone-local batch selection
- raw scrape ingestion
- control-layer completion tracking
- canonical forecast processing
- daily presentation publishing
- long-term historical storage

For the top-level bucket layout, see [Storage Layout](storage-layout.md). For the historical table shapes, see [Forecast Schema](forecast-schema.md).

## Summary

The forecast domain should use the same layered approach as discovery, but with a different batch boundary.

The authoritative batch unit is:

- `timezone`
- `local_batch_date`
- `scheduled_local_time`

Each batch represents "all forecast scrapes that should run for all live spots in one timezone at one specific local time."

The pipeline is:

1. An hourly UTC scheduler tick evaluates which timezone-local batches are due.
2. A batch manifest is written to `control/` with the expected set of `spot_id`s.
3. One raw forecast object is written per spot to `raw/forecast/...`.
4. Each successful scrape writes a per-spot completion marker.
5. When all expected spots are complete, the batch is marked ready for processing.
6. A forecast processor package reads the batch, writes canonical forecast outputs, publishes the presentation layer, and appends historical rows.

## Batch Model

### Why timezone-local batches

Forecast notifications are consumed in local surf-day terms, not UTC-hour terms. A batch therefore needs to align to the local day in the spot's timezone.

This keeps:

- scrape timing aligned with when customers experience the day
- completion logic deterministic
- presentation artifacts aligned to text-notification windows

### Required batch fields

Every planned forecast batch should carry:

| Field | Meaning |
|-------|---------|
| `batch_id` | Stable identifier for one timezone-local scrape batch |
| `timezone` | IANA timezone, such as `Europe/London` |
| `local_batch_date` | Local calendar day for the batch |
| `scheduled_local_time` | Local time that defines when the batch should run |
| `scheduled_utc_time` | UTC equivalent for operational tracing |
| `expected_spot_count` | Number of live spots expected in the batch |
| `completed_spot_count` | Number of completion markers observed |
| `batch_status` | `planned`, `in_progress`, `complete`, `processing`, `published`, or `failed` |

### Spot membership source

Batch membership should come from the latest discovery catalog:

- read live spots from `processed/discovery/catalog_latest/...`
- group them by `timezone`
- enumerate the `spot_id`s for the due timezone batch

`spot_id` is the join key between the forecast domain and the spot/discovery domain.

## Layer Responsibilities

### Raw layer

`raw/forecast/...` stores one immutable source envelope per successful spot scrape.

Recommended key:

```text
raw/forecast/timezone=<tz>/local_date=YYYY-MM-DD/batch_id=<batch_id>/spot_id=<spot_id>/run_id=<run_id>.json.gz
```

The raw payload should remain close to the combined Surfline source shape and include batch metadata alongside the scrape metadata.

### Control layer

`control/` stores the operational objects that define completeness and drive downstream processing.

Recommended objects:

```text
control/
  manifests/
    forecast_batches/
      timezone=<tz>/
        local_date=YYYY-MM-DD/
          batch_id=<batch_id>.json
    processing/
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
    forecast/
      latest_batch_by_timezone/
        timezone=<tz>.json
```

Control objects have distinct roles:

- batch manifest: expected membership for one timezone-local batch
- per-spot completion marker: proves one member scrape finished successfully
- processing manifest: proves the batch is complete and ready for downstream transformation
- checkpoint: records the latest published batch state per timezone

### Canonical layer

`processed/forecast/canonical/...` stores normalized per-spot outputs derived from the completed batch.

Recommended key:

```text
processed/forecast/canonical/timezone=<tz>/local_date=YYYY-MM-DD/batch_id=<batch_id>/spot_id=<spot_id>/forecast.json.gz
```

The canonical layer is the stable forecast business model, decoupled from Surfline's raw JSON layout.

### Presentation layer

`processed/forecast/presentation/...` stores notification-ready daily outputs, published once per timezone-local day.

Recommended key:

```text
processed/forecast/presentation/timezone=<tz>/local_date=YYYY-MM-DD/forecast_summary.parquet
```

This layer exists for customer-facing alert generation and should be built from canonical outputs, not directly from raw scrapes.

### History layer

`processed/forecast/history/...` stores append-only Parquet for long-term analysis and future warehouse loading.

Recommended layout:

```text
processed/forecast/history/
  fact_rating/year=YYYY/month=MM/forecast_date=YYYY-MM-DD/part-*.parquet
  fact_wave/year=YYYY/month=MM/forecast_date=YYYY-MM-DD/part-*.parquet
  fact_swells/year=YYYY/month=MM/forecast_date=YYYY-MM-DD/part-*.parquet
  fact_wind/year=YYYY/month=MM/forecast_date=YYYY-MM-DD/part-*.parquet
  fact_weather/year=YYYY/month=MM/forecast_date=YYYY-MM-DD/part-*.parquet
  fact_tides/year=YYYY/month=MM/forecast_date=YYYY-MM-DD/part-*.parquet
  dim_sunlight/year=YYYY/month=MM/forecast_date=YYYY-MM-DD/part-*.parquet
```

`spot_id` should stay as a first-class column in every table and may be used as a secondary partition only if file-size testing shows it is necessary.

## Completion And Processing Rules

### Batch creation

When an hourly scheduler tick determines that a timezone-local scrape time is due:

1. read the latest discovery catalog
2. select live spots in that timezone
3. write the batch manifest
4. enqueue one scrape job per `spot_id`

### Scrape completion

Each successful scrape should write:

1. one raw forecast object
2. one completion marker tied to the same `batch_id` and `spot_id`

### Batch completion

A batch is complete when:

- every expected `spot_id` from the batch manifest has a completion marker
- no additional membership decisions remain unresolved for that batch

Raw object creation alone does not define completeness. Completeness is manifest-driven.

### Processing-ready event

When a batch becomes complete:

1. write a processing manifest under `control/manifests/processing/domain=forecast/...`
2. trigger the forecast processor package using that manifest

## Canonical Forecast Contract

Every canonical forecast object should include at least:

| Field | Notes |
|-------|-------|
| `spot_id` | Shared business key with discovery |
| `timezone` | Spot timezone used for batching and presentation |
| `local_batch_date` | Local publication day for the batch |
| `batch_id` | Batch lineage key |
| `scraped_at` | Raw scrape timestamp |
| `forecast_valid_at` | Forecast timestamp represented by each row or entry |
| `source_run_id` | Raw scrape run identifier |
| `source_raw_key` | Raw object lineage |
| `processor_version` | Canonicalization version |
| `schema_version` | Canonical schema version |

The canonical model should normalize the six Surfline forecast payloads into one stable forecast object keyed by `spot_id` and batch metadata.

## Presentation Contract

The presentation layer should be published once per `timezone + local_batch_date`.

Each row should be suitable for alert generation and include:

| Field | Notes |
|-------|-------|
| `spot_id` | Join key to discovery and customer preferences |
| `timezone` | Publication boundary |
| `local_batch_date` | Notification day |
| `batch_id` | Traceability to the source batch |
| `quality_score` | Ranking field for "looks good" detection |
| `best_window_start` | First forecast time worth notifying on |
| `best_window_end` | Last forecast time worth notifying on |
| `headline` | Short presentation summary |
| `eligible_for_alert` | Boolean notification gate |

Exact scoring logic can evolve, but the publication unit should stay timezone-day based.

## Warehouse-Oriented History Guidance

The historical layer should be optimized for future warehouse loading.

Document these defaults:

- append-only Parquet
- `snappy` compression
- time-first partitions using `forecast_date`
- compact multiple spots into larger files
- avoid one file per spot per scrape in the long-term history layer

This keeps S3 object counts reasonable and aligns better with Athena, DuckDB, and future warehouse ingestion patterns.

## Triggered Packages

The target forecast flow should be described as a set of smaller packages:

- scheduler or dispatcher: determines due timezone batches
- forecast scraper: writes raw per-spot source envelopes
- forecast batch completion checker: emits processing-ready manifests
- forecast processor: writes canonical, presentation, and history outputs

See [Forecast Processors](../packages/forecast-processors.md) for the package-level responsibilities.
