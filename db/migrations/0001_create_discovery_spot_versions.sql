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
  href text null,
  breadcrumbs jsonb null,
  subregion jsonb null,
  travel_details jsonb null,
  source_run_id text not null,
  source_raw_key text not null,
  source_type text not null check (source_type in ('sitemap', 'spot_report')),
  schema_version integer not null default 1,
  created_at timestamptz not null default now(),

  constraint discovery_spot_versions_required_added_fields check (
    event_type = 'removed'
    or (
      spot_id is not null
      and name is not null
      and lat is not null
      and lon is not null
      and timezone is not null
      and utc_offset is not null
      and abbr_timezone is not null
      and href is not null
    )
  )
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
