# Forecast Pipeline

> **Status: PLANNED** | Target v1 orchestration and storage model for forecast ingestion into Supabase/Postgres

This page defines the v1 forecast pipeline end to end:

- hourly scheduling
- UTC-offset forecast run selection
- raw scrape ingestion
- DynamoDB control-state tracking
- per-spot forecast processing into Supabase/Postgres
- later historical archive/offload

For table shapes, see [Forecast Schema](forecast-schema.md).

## Summary

The forecast domain uses the same broad layered approach as discovery, but v1 avoids S3 control manifests. DynamoDB is the control state store; S3 stores only successful raw forecast payloads.

The authoritative run unit is:

- `utc_offset`
- UTC `scrape_date`
- configured local scrape time

Each forecast run represents all live spots whose stored integer UTC offset makes them due for forecast scraping at the configured local scrape time.

The v1 pipeline is:

1. An hourly EventBridge schedule directly invokes the Forecast Run Planner.
2. The planner uses EventBridge `time` as the scheduled UTC tick time.
3. The planner computes the due UTC offset from the configured local scrape time and offset range.
4. The planner queries Supabase/Postgres processed discovery state for live spots with that `utc_offset`.
5. If no spots are due, no run is created.
6. If spots are due, the planner conditionally creates a DynamoDB forecast run and planned spot items.
7. The planner enqueues one forecast scrape message per `spot_id`.
8. The Forecast Scraper fetches surf-relevant forecast endpoints and writes one raw S3 object per successful spot scrape.
9. The scraper emits a terminal completion message for every caught scrape outcome.
10. The Forecast Spot Processor consumes completion messages, updates DynamoDB scrape/processing control state, and writes successful forecasts to Supabase/Postgres.

## Run Model

### Why UTC-offset forecast runs

The planner selects spots by stored integer `utc_offset` so each hourly tick performs a narrow Supabase/Postgres query instead of loading the full live spot catalog. IANA timezones remain useful spot metadata, but they are not the v1 scheduling authority.

This deliberately accepts DST/stale-offset imperfections in exchange for cheap and predictable selection.

### Required run fields

Every planned forecast run should carry:

| Field | Meaning |
|-------|---------|
| `forecast_run_id` | Stable identifier for one offset/date/local-time forecast run |
| `utc_offset` | Stored integer offset used to select due spots |
| `scrape_date` | UTC date of the scheduled EventBridge tick |
| `local_date` | Date at the configured local scrape time for the selected offset |
| `scheduled_utc_time` | EventBridge scheduled UTC timestamp |
| `configured_local_time` | Configured scrape time, e.g. `04:00` |
| `expected_scrape_count` | Number of planned spot scrapes |
| `terminal_scrape_count` | Number of spot scrapes that reached `success` or `failed` |
| `successful_scrape_count` | Number of spot scrapes that produced usable raw forecast objects |
| `failed_scrape_count` | Number of spot scrapes that failed without usable raw forecast objects |
| `expected_processing_count` | Number of successful scrapes expected to be processed |
| `terminal_processing_count` | Number of processing attempts that reached success or failure |
| `successful_processing_count` | Number of successful scrape payloads written to Supabase/Postgres |
| `failed_processing_count` | Number of successful scrape payloads that failed processing |
| `run_status` | `planned`, `in_progress`, or `complete` |
| `scrape_status` | `in_progress`, `complete`, or `complete_with_failures` |
| `processing_status` | `not_started`, `in_progress`, `complete`, or `complete_with_failures` |

Recommended deterministic ID:

```text
forecast#offset=<utc_offset>#scrape_date=YYYY-MM-DD#time=HH-MM
```

Example:

```text
forecast#offset=13#scrape_date=2026-05-21#time=04-00
```

### Spot membership source

Forecast run membership comes from Supabase/Postgres processed discovery state:

- select current live spots
- filter by stored `utc_offset`
- return `spot_id`, `spot_version_id`, `name`, `utc_offset`, `timezone`, `lat`, and `lon`

`spot_id` is the join key between the forecast domain and the spot/discovery domain.

## Layer Responsibilities

### Raw layer

`raw/forecast/...` stores one immutable source envelope per successful spot scrape.

Recommended key:

```text
raw/forecast/scrape_date=YYYY-MM-DD/utc_offset=<offset>/forecast_run_id=<forecast_run_id>/spot_id=<spot_id>.json.gz
```

The raw envelope should include only useful scrape/run lineage and the selected Surfline source payloads:

```json
{
  "schema_version": 1,
  "source_type": "forecast",
  "forecast_run_id": "...",
  "spot_id": "...",
  "spot_version_id": "...",
  "spot_name": "...",
  "scraped_at": "2026-05-21T15:03:12Z",
  "scheduled_utc_time": "2026-05-21T15:00:00Z",
  "utc_offset": 13,
  "timezone": "Pacific/Auckland",
  "lat": -36.8,
  "lon": 174.7,
  "raw_payload": {
    "rating": {},
    "tides": {},
    "wave": {},
    "wind": {}
  }
}
```

Failed scrapes do not write raw objects.

### Control layer

Forecast v1 control state lives in DynamoDB, not S3.

Recommended key shape:

```text
pk = RUN#<forecast_run_id>
sk = RUN

pk = RUN#<forecast_run_id>
sk = SPOT#<spot_id>
```

The run item tracks aggregate counts and statuses. Planned spot items track scrape status, raw lineage, processing claims, processing status, and failure details.

Per-spot failure fields:

```text
scrape_failure_source
scrape_failure_reason
processing_failure_source
processing_failure_reason
```

Control state TTL is 7 days.

### Supabase/Postgres live forecast layer

Successful raw forecasts are transformed per spot and inserted into forecast star schema tables in Supabase/Postgres:

```text
forecast_fact_rating
forecast_fact_wave
forecast_fact_swells
forecast_fact_wind
forecast_fact_tides
```

Writes are append-only with unique constraints for idempotency and `ON CONFLICT DO NOTHING`. All five tables for one spot/run are written in one transaction.

### Historical archive layer

Long-term Parquet archive/offload and Postgres retention are out of scope for v1. Tables should include `scraped_at` indexes so later manual or automated deletion is efficient.

## Completion And Processing Rules

### Run creation

When the hourly planner receives an EventBridge tick:

1. parse `event.time` as the scheduled UTC time
2. compute due offset(s) from `FORECAST_SCRAPE_LOCAL_TIME`, `FORECAST_MIN_UTC_OFFSET`, and `FORECAST_MAX_UTC_OFFSET`
3. query Supabase/Postgres for live spots matching the due offset
4. if zero spots are returned, exit without creating a run
5. conditionally create the DynamoDB run item
6. seed planned spot items
7. batch-send SQS scrape messages
8. mark the run `in_progress` last

If a duplicate planner invocation creates the same `forecast_run_id`, the conditional DynamoDB write makes the duplicate exit safely.

### Scrape completion

A forecast spot scrape is all-or-nothing across the collected endpoints:

```text
rating
tides
wave
wind
```

A terminal scrape success means all four endpoint payloads were fetched and parsed successfully and one raw S3 object was written.

A terminal scrape failure means no usable raw forecast object exists. The scraper sends a failed completion message immediately for caught scrape/fetch/parse failures. Infrastructure failures, such as inability to send the completion message, may still raise.

### Per-spot processing

The Forecast Spot Processor consumes completion messages with SQS batch size 1.

For each first-seen terminal scrape completion:

1. conditionally record scrape terminal status in DynamoDB
2. increment scrape counters once
3. if the scrape failed, skip Postgres writes
4. if the scrape succeeded, claim processing in DynamoDB
5. read the raw S3 object
6. transform rating, wave, swells, wind, and tides
7. insert all rows into Supabase/Postgres in one transaction
8. mark processing terminal in DynamoDB
9. update aggregate statuses if the run is now complete

Processing claims can be reclaimed after 5 minutes if stuck in `processing`.

### Run completion

A run is complete when:

```text
terminal_scrape_count == expected_scrape_count
AND terminal_processing_count == expected_processing_count
```

Scrape and processing rollup statuses independently record whether failures occurred:

```text
scrape_status = complete | complete_with_failures
processing_status = complete | complete_with_failures
```

Processing expected count is based on successful scrapes, not planned scrapes.

## Surf-Relevant Forecast Contract

V1 only collects forecast source data relevant to surf conditions:

- rating
- wave
- swells derived from wave
- wind
- tides

Weather and sunlight are intentionally not collected or stored in v1.

Every forecast fact row should include lineage columns such as:

| Field | Notes |
|-------|-------|
| `forecast_run_id` | Forecast run lineage key |
| `spot_id` | Shared business key with discovery |
| `spot_version_id` | Discovery version used at planning time |
| `forecast_ts` | Forecast timestamp represented by the row |
| `scraped_at` | Actual UTC scrape timestamp |
| `scheduled_utc_time` | EventBridge scheduled UTC timestamp |
| `source_raw_key` | Raw S3 object lineage |
| `schema_version` | Forecast schema version |
| `created_at` | Row creation timestamp |

## Triggered Packages

The v1 forecast flow uses these packages:

- `forecast_run_planner`: determines due UTC-offset forecast runs, creates DynamoDB control state, and enqueues scrapes
- `forecast_scraper`: writes raw per-spot source envelopes and emits terminal completion messages
- `forecast_spot_processor`: records scrape outcomes, processes successful spot payloads into Supabase/Postgres, and updates run completion state

See [Forecast Processors](../packages/forecast-processors.md) for package-level responsibilities.
