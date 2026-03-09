# Forecast Processors

> **Status: PLANNED** | Event-driven packages for forecast batch completion, canonicalization, presentation publishing, and history writes

The target forecast flow should be split into small processors, similar to the discovery setup, with the batch boundary defined by `timezone + local_batch_date + scheduled_local_time`.

For the batch and storage model, see [Forecast Pipeline](../data_architecture/forecast-pipeline.md).

## Planned Packages

### `packages/jobs/forecast_batch_planner`

Triggered by the hourly scheduler tick.

Responsibilities:

- read the latest discovery catalog
- group live spots by timezone
- determine which timezone-local batches are due
- write one batch manifest per due timezone batch
- enqueue one forecast scrape request per `spot_id`

### `packages/jobs/forecast_batch_completion`

Triggered by raw forecast writes or completion marker writes.

Responsibilities:

- read the batch manifest for the relevant `batch_id`
- count observed completion markers
- detect when the batch reaches expected membership
- write a processing-ready manifest to `control/manifests/processing/domain=forecast/...`

### `packages/jobs/forecast_processor`

Triggered from a completed forecast processing manifest.

Responsibilities:

- read all raw forecast objects in the completed batch
- validate that raw coverage matches the batch manifest
- transform each raw payload into the canonical forecast model
- write canonical outputs under `processed/forecast/canonical/...`
- publish the timezone-day presentation layer under `processed/forecast/presentation/...`
- append history rows to `processed/forecast/history/...`

## Trigger Model

Recommended trigger pattern:

- hourly scheduler tick -> `forecast_batch_planner`
- raw forecast completion markers -> `forecast_batch_completion`
- completed processing manifest -> `forecast_processor`

This keeps scheduling, completion detection, and transformation separate.

## Why Split The Processors

Compared to one monolithic forecast pipeline Lambda, this design:

- mirrors the discovery control-plane pattern
- makes batch completeness explicit
- supports safe replay at the batch level
- keeps notification publication aligned to timezone-local days
- separates raw scrape collection from downstream business modeling
