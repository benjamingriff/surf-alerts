# Context Glossary

## Processed Spot Discovery State

The canonical, queryable representation of Surfline spot discovery after raw payloads have been interpreted. This includes the current spot catalog and historical spot versions. Processed spot discovery state lives in RDS Postgres and is the source for selecting live spots due for forecast scraping.

## Spot Lifecycle Event

A business state transition persisted in processed spot discovery state. For the first implementation, the only persisted spot lifecycle events are `added` and `removed`. Existing unchanged spots are no-ops, and scrape failures belong to pipeline control state rather than spot lifecycle history.

## Spot Removal Tombstone

The current processed spot discovery version that records a previously known spot as removed. Removing a spot closes the previous current version and inserts a new current version with `event_type = removed`, allowing the system to distinguish a spot that was never seen from one that was seen and later removed.

## Raw Evidence Layer

Immutable raw scraper payloads stored in S3. Raw files are retained for audit, replay, and recovery, but they are not the canonical processed state.

## Scraper Completion Signal

An explicit message emitted by a scraper after it reaches a terminal outcome. A success signal means the referenced raw S3 object has already been written and is ready for downstream processing. A failure signal means no processed spot state should be created from that scrape attempt.

## Pipeline Control State

Temporary orchestration state used to make pipeline execution idempotent and observable, such as discovery runs, forecast runs, expected scrape counts, scrape completions, processing completions, planner manifests, and failures. Pipeline control state is not business spot state.

## Planner Manifest

A run-scoped control document that records the planner's discovery classification, including added spot IDs, removed spot IDs, source sitemap raw key, and planning counts. A planner manifest is control state, not processed spot discovery state.

## Scrape Failure

A terminal scrape outcome where no usable raw payload was produced and no processed spot discovery state should be created. Scrape failures are recorded in pipeline control state for monitoring and do not create spot lifecycle events.

## Terminal Scrape Outcome

The final recorded outcome for one planned scrape attempt. Terminal scrape outcomes are `success` and `failed`. A success means the raw S3 object exists and its key is recorded; a failure means no usable raw object exists and a failure reason is recorded. Both outcomes count toward run completion.

## Discovery Run

One scheduled sitemap scrape and all downstream work needed to reconcile processed spot discovery state from that sitemap. A discovery run can complete even if some individual spot scrapes fail; those failures belong to pipeline control state, not processed spot discovery state. Spot report processing happens as a batch after the run's expected spot scrapes have all reached a terminal scrape outcome.

## Forecast Run

All live spots whose stored UTC offset makes them due for forecast scraping at one configured local scrape time. Forecast runs are offset-selected for operational efficiency; IANA timezones remain descriptive spot metadata rather than the scheduling authority. A forecast run is identified deterministically from its UTC offset, UTC scrape date, and scheduled local time so repeated scheduler attempts refer to the same work.

## Scrape Date

The UTC calendar date on which scraper work is scheduled or collected. Scrape date is process metadata and is not the local surf date for a spot or forecast run.

## Forecast Partition Day

The UTC calendar day derived from a forecast fact's scheduled UTC time. Forecast partition days group facts by when the scrape was supposed to run, not by when the scrape actually completed.

## Forecast Run Planner

The pipeline role that creates a forecast run and its expected spot scrape membership. A forecast run planner belongs to pipeline control state and does not create forecast facts.

## Forecast Hot Store

The short-term, queryable store of processed forecast facts. Forecast hot store data is retained for three daily partitions: one live query day, one archive-processing day, and one recovery buffer day.

## Forecast Archive

The durable historical store of processed forecast facts after they leave the forecast hot store. The forecast archive is intended to preserve full forecast history independently of raw scraper payload retention.
