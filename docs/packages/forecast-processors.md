# Forecast Processors

> **Status: PLANNED** | Event-driven packages for forecast run planning and per-spot forecast processing

The v1 forecast flow is split into small packages, with run control state stored in DynamoDB and live forecast facts stored in Supabase/Postgres.

For the run and storage model, see [Forecast Pipeline](../data_architecture/forecast-pipeline.md).

## Planned Packages

### `packages/jobs/forecast_run_planner`

Triggered directly by an hourly EventBridge scheduled event.

Responsibilities:

- use EventBridge `time` as the scheduled UTC tick time
- read `FORECAST_SCRAPE_LOCAL_TIME`, `FORECAST_MIN_UTC_OFFSET`, and `FORECAST_MAX_UTC_OFFSET`
- compute the due stored UTC offset for the configured local scrape time
- query Supabase/Postgres processed discovery state for current live spots with that `utc_offset`
- skip run creation when no live spots are due
- build deterministic `forecast_run_id`
- conditionally create the DynamoDB forecast run item
- seed DynamoDB planned spot items
- batch-send one forecast scrape SQS message per `spot_id`
- mark the run `in_progress` after scrape messages have been sent

The planner does not write S3 control manifests in v1.

### `packages/scrapers/forecast_scraper`

Triggered by the forecast scrape SQS queue.

Responsibilities:

- consume one planned spot scrape message at a time
- fetch the surf-relevant Surfline forecast endpoints:
  - rating
  - tides
  - wave
  - wind
- treat scrape success as all-or-nothing across those four endpoints
- write one raw gzipped S3 envelope for successful scrapes
- send a terminal completion message for every caught scrape outcome
- send no raw S3 object for failed scrapes

### `packages/jobs/forecast_spot_processor`

Triggered by the forecast completion SQS queue with batch size 1.

Responsibilities:

- consume one terminal forecast scrape completion message at a time
- conditionally record scrape terminal status in DynamoDB
- increment scrape counters once per planned spot
- skip Postgres writes for failed scrapes
- claim processing for successful scrapes, with stale claim reclaim after 5 minutes
- read the successful raw forecast object from S3
- transform raw payloads into forecast star schema rows:
  - `forecast_fact_rating`
  - `forecast_fact_wave`
  - `forecast_fact_swells`
  - `forecast_fact_wind`
  - `forecast_fact_tides`
- insert all five table sets in one Supabase/Postgres transaction
- use append-only inserts with unique constraints and `ON CONFLICT DO NOTHING`
- mark processing success or failure in DynamoDB
- update aggregate run status when all expected scrape and processing work is terminal

The forecast spot processor replaces the earlier planned separate completion checker for v1.

## Trigger Model

Recommended v1 trigger pattern:

```text
EventBridge hourly schedule
  -> forecast_run_planner
  -> forecast scrape SQS queue
  -> forecast_scraper
  -> forecast completion SQS queue
  -> forecast_spot_processor
  -> Supabase/Postgres forecast tables
```

## Control State

Forecast v1 uses DynamoDB for control state only. It does not write S3 control manifests or S3 completion markers.

DynamoDB stores:

- one run item per `forecast_run_id`
- one planned spot item per `forecast_run_id + spot_id`
- scrape terminal status and failure details
- processing claim/status and failure details
- aggregate scrape and processing counts

Control-state TTL is 7 days.

## Why This Split

Compared to one monolithic forecast pipeline Lambda, this design:

- mirrors the discovery run planner language
- keeps hourly run planning separate from high-volume per-spot work
- avoids loading an entire forecast run into memory
- processes each successful spot forecast independently
- keeps scraper responsibilities focused on raw collection
- keeps DynamoDB as the idempotent control plane
- allows later archive/presentation processors to be added without changing scrape collection
