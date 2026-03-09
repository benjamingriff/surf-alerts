# Discovery Schema

> **Status: PLANNED** | Versioned Parquet model for spot discovery and metadata history

This page defines the **discovery analytics and serving sublayer** stored under `processed/discovery/`.

Discovery data uses **logical SCD2 semantics** with **physical append-only writes**:

- every detected state transition creates a new version row
- no existing Parquet row is updated in place
- the current catalog is derived from the latest `version_ts` per `spot_id`

For the broader bucket layout, see [Storage Layout](storage-layout.md).

## Schema Diagram

```text
                           ┌──────────────────────┐
                           │   dim_spots_core     │
                           │──────────────────────│
                           │ spot_version_id (PK) │
                           │ spot_id              │
                           │ version_ts           │
                           │ content_checksum     │
                           │ event_type           │
                           │ seen_at              │
                           │ sitemap_link         │
                           │ forecast_link        │
                           └──────────┬───────────┘
                                      │
        ┌─────────────────────────────┼─────────────────────────────┐
        │               │             │             │               │
        ▼               ▼             ▼             ▼               ▼
 ┌───────────────┐ ┌──────────────┐ ┌────────────┐ ┌─────────────┐ ┌──────────────────┐
 │dim_spot_      │ │dim_spot_     │ │dim_spot_   │ │dim_spot_    │ │dim_spot_travel_  │
 │location       │ │breadcrumbs   │ │cameras     │ │board_types  │ │details           │
 │───────────────│ │──────────────│ │────────────│ │─────────────│ │──────────────────│
 │spot_version_id│ │spot_version_id│ │spot_version_id│spot_version_id│spot_version_id │
 │spot_id        │ │spot_id       │ │spot_id     │ │spot_id      │ │spot_id           │
 │name           │ │breadcrumb_idx│ │camera_idx  │ │board_type   │ │description       │
 │lat, lon       │ │name          │ │camera_id   │ │...          │ │best_size         │
 │timezone       │ │href          │ │title       │ └─────────────┘ │hazards           │
 │subregion_name │ └──────────────┘ │...         │                 │...               │
 └───────────────┘                  └────────────┘                 └──────────────────┘

                           ┌──────────────────────┐
                           │  discovery_events    │
                           │──────────────────────│
                           │ event_ts             │
                           │ spot_id              │
                           │ event_type           │
                           │ old_checksum         │
                           │ new_checksum         │
                           │ spot_version_id      │
                           └──────────────────────┘
```

## Core Principles

1. `dim_spots_core` is the version anchor table.
2. Child dimension rows are keyed by `spot_version_id`, not just `spot_id`.
3. `removed` is represented by a tombstone row in `dim_spots_core`.
4. Child rows are only written for content-bearing versions.
5. Current state is defined by the row with the maximum `version_ts` for each `spot_id`.

## Table Definitions

### dim_spots_core

Append-only version table that defines lifecycle and version identity for each spot.

| Column | Type | Notes |
|--------|------|-------|
| `spot_version_id` | STRING | Primary key for a single versioned spot record |
| `spot_id` | STRING | Natural key from Surfline |
| `version_ts` | TIMESTAMP | Timestamp assigned to this version event |
| `content_checksum` | STRING | SHA256 over the canonicalized spot object |
| `event_type` | STRING | `added`, `changed`, or `removed` |
| `seen_at` | TIMESTAMP | When the spot first appeared in the upstream run that created this version |
| `sitemap_link` | STRING | Main report URL from sitemap or canonicalized report payload |
| `forecast_link` | STRING | Forecast URL from sitemap when available |
| `source_run_id` | STRING | Ingest/processor run that created the version |
| `source_raw_key` | STRING | Raw object key that produced the version |
| `source_type` | STRING | `sitemap` or `spot_report` |
| `schema_version` | INT32 | Discovery schema version |
| `processed_at` | TIMESTAMP | Processor timestamp |

**Semantics:**

- `added` rows represent first-seen active spots
- `changed` rows represent a new checksum for an existing spot
- `removed` rows are tombstone versions with no child dimension rows

### dim_spot_location

Frequently filtered flat fields used by the scraper and API.

| Column | Type | Notes |
|--------|------|-------|
| `spot_version_id` | STRING | Foreign key to `dim_spots_core` |
| `spot_id` | STRING | Convenience natural key |
| `name` | STRING | Spot display name |
| `lat` | FLOAT64 | Latitude |
| `lon` | FLOAT64 | Longitude |
| `timezone` | STRING | IANA timezone |
| `utc_offset` | INT32 | Offset hours from UTC |
| `abbr_timezone` | STRING | Abbreviated timezone label |
| `subregion_id` | STRING | Surfline subregion identifier when present |
| `subregion_name` | STRING | Surfline subregion name |

### dim_spot_breadcrumbs

Normalized breadcrumb trail for a spot version.

| Column | Type | Notes |
|--------|------|-------|
| `spot_version_id` | STRING | Foreign key to `dim_spots_core` |
| `spot_id` | STRING | Convenience natural key |
| `breadcrumb_index` | INT32 | Original breadcrumb order |
| `name` | STRING | Breadcrumb label |
| `href` | STRING | Breadcrumb href when present |

### dim_spot_cameras

Spot cameras captured from `/reports`.

| Column | Type | Notes |
|--------|------|-------|
| `spot_version_id` | STRING | Foreign key to `dim_spots_core` |
| `spot_id` | STRING | Convenience natural key |
| `camera_index` | INT32 | Original array order |
| `camera_id` | STRING | Surfline camera identifier |
| `title` | STRING | Camera title |
| `stream_url` | STRING | Live stream URL |
| `still_url` | STRING | Still image URL |
| `is_premium` | BOOLEAN | Premium access flag |

### dim_spot_ability_levels

| Column | Type | Notes |
|--------|------|-------|
| `spot_version_id` | STRING | Foreign key to `dim_spots_core` |
| `spot_id` | STRING | Convenience natural key |
| `ability_index` | INT32 | Original array order |
| `ability_level` | STRING | Ability enum |

### dim_spot_board_types

| Column | Type | Notes |
|--------|------|-------|
| `spot_version_id` | STRING | Foreign key to `dim_spots_core` |
| `spot_id` | STRING | Convenience natural key |
| `board_type_index` | INT32 | Original array order |
| `board_type` | STRING | Board type enum |

### dim_spot_travel_details

Travel and qualitative metadata for a versioned spot record.

| Column | Type | Notes |
|--------|------|-------|
| `spot_version_id` | STRING | Foreign key to `dim_spots_core` |
| `spot_id` | STRING | Convenience natural key |
| `description` | STRING | Narrative description |
| `access` | STRING | Access notes |
| `hazards` | STRING | Hazard summary |
| `best_size` | STRING | Best size description |
| `crowd_factor` | STRING | Crowd summary |
| `spot_rating` | INT32 | Qualitative rating |
| `break_types_json` | STRING | Canonical JSON array |
| `best_seasons_json` | STRING | Canonical JSON array |
| `best_tides_json` | STRING | Canonical JSON array |
| `best_swell_directions_json` | STRING | Canonical JSON array |
| `best_wind_directions_json` | STRING | Canonical JSON array |
| `bottom_json` | STRING | Canonical JSON array |

### discovery_events

Append-only event log for lifecycle changes.

| Column | Type | Notes |
|--------|------|-------|
| `event_ts` | TIMESTAMP | Event creation timestamp |
| `run_id` | STRING | Processor run identifier |
| `spot_id` | STRING | Surfline spot ID |
| `event_type` | STRING | `added`, `changed`, or `removed` |
| `source_type` | STRING | `sitemap` or `spot_report` |
| `source_raw_key` | STRING | Raw S3 object key |
| `old_checksum` | STRING | Previous checksum when applicable |
| `new_checksum` | STRING | New checksum when applicable |
| `spot_version_id` | STRING | New version created by this event, if any |
| `version_ts` | TIMESTAMP | Version timestamp associated with the event |

## Current State Query Pattern

The current catalog is derived from the latest version row for each `spot_id`.

```sql
WITH ranked AS (
  SELECT
    *,
    ROW_NUMBER() OVER (
      PARTITION BY spot_id
      ORDER BY version_ts DESC
    ) AS row_num
  FROM dim_spots_core
)
SELECT *
FROM ranked
WHERE row_num = 1
  AND event_type <> 'removed';
```

Then join child tables on `spot_version_id`.

## Serving Snapshot

Although the version tables are the source of truth, the system should materialize a serving snapshot under `processed/discovery/catalog_latest/`.

This snapshot should contain:

- one Parquet file per discovery dimension table
- only the latest version per `spot_id`
- no tombstone latest rows

The scraper and future API should read this snapshot for operational workloads.

## Why This Model

This design keeps the advantages of a split dimension model while fitting immutable object storage:

- full history for every version of a spot
- append-only writes only
- no Parquet rewrites to mark older rows inactive
- simple joins via `spot_version_id`
- fast operational reads via the derived latest snapshot
