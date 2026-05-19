create table if not exists discovery_spot_versions (
  spot_version_id text primary key,
  spot_id text not null,
  event_type text not null check (event_type in ('added', 'removed')),
  is_current boolean not null,
  valid_from timestamptz not null,
  valid_to timestamptz null,
  content_checksum text null,
  name text null,
  lat double precision null,
  lon double precision null,
  timezone text null,
  utc_offset integer null,
  abbr_timezone text null,
  subregion_id text null,
  subregion_name text null,
  sitemap_link text null,
  forecast_link text null,
  breadcrumbs jsonb null,
  cameras jsonb null,
  ability_levels jsonb null,
  board_types jsonb null,
  travel_details jsonb null,
  source_run_id text not null,
  source_raw_key text not null,
  source_type text not null check (source_type in ('sitemap', 'spot_report')),
  schema_version integer not null,
  created_at timestamptz not null default now()
);

create unique index if not exists discovery_spot_versions_one_current_per_spot
  on discovery_spot_versions (spot_id)
  where is_current = true;
create index if not exists discovery_spot_versions_spot_valid_from_idx
  on discovery_spot_versions (spot_id, valid_from desc);
create index if not exists discovery_spot_versions_current_event_idx
  on discovery_spot_versions (is_current, event_type);
create index if not exists discovery_spot_versions_source_run_idx
  on discovery_spot_versions (source_run_id);
