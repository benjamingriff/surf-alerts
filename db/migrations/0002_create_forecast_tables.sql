create table if not exists forecast_fact_rating (
  forecast_run_id text not null,
  spot_id text not null,
  spot_version_id text not null,
  forecast_ts timestamptz not null,
  scraped_at timestamptz not null,
  scheduled_utc_time timestamptz not null,
  utc_offset integer null,
  timezone text null,
  rating_key text null,
  rating_value double precision null,
  source_utc_offset integer null,
  run_init_ts timestamptz null,
  source_raw_key text not null,
  schema_version integer not null default 1,
  created_at timestamptz not null default now(),

  constraint forecast_fact_rating_pk unique (forecast_run_id, spot_id, forecast_ts)
);

create table if not exists forecast_fact_wave (
  forecast_run_id text not null,
  spot_id text not null,
  spot_version_id text not null,
  forecast_ts timestamptz not null,
  scraped_at timestamptz not null,
  scheduled_utc_time timestamptz not null,
  utc_offset integer null,
  timezone text null,
  surf_min integer null,
  surf_max integer null,
  surf_plus boolean null,
  surf_human_relation text null,
  surf_raw_min double precision null,
  surf_raw_max double precision null,
  surf_optimal_score integer null,
  power double precision null,
  probability integer null,
  source_utc_offset integer null,
  location_lon double precision null,
  location_lat double precision null,
  forecast_location_lon double precision null,
  forecast_location_lat double precision null,
  offshore_location_lon double precision null,
  offshore_location_lat double precision null,
  run_init_ts timestamptz null,
  source_raw_key text not null,
  schema_version integer not null default 1,
  created_at timestamptz not null default now(),

  constraint forecast_fact_wave_pk unique (forecast_run_id, spot_id, forecast_ts)
);

create table if not exists forecast_fact_swells (
  forecast_run_id text not null,
  spot_id text not null,
  spot_version_id text not null,
  forecast_ts timestamptz not null,
  swell_index integer not null,
  scraped_at timestamptz not null,
  scheduled_utc_time timestamptz not null,
  utc_offset integer null,
  timezone text null,
  height double precision null,
  period integer null,
  impact double precision null,
  power double precision null,
  direction double precision null,
  direction_min double precision null,
  optimal_score integer null,
  source_raw_key text not null,
  schema_version integer not null default 1,
  created_at timestamptz not null default now(),

  constraint forecast_fact_swells_pk unique (forecast_run_id, spot_id, forecast_ts, swell_index)
);

create table if not exists forecast_fact_wind (
  forecast_run_id text not null,
  spot_id text not null,
  spot_version_id text not null,
  forecast_ts timestamptz not null,
  scraped_at timestamptz not null,
  scheduled_utc_time timestamptz not null,
  utc_offset integer null,
  timezone text null,
  speed double precision null,
  gust double precision null,
  direction double precision null,
  direction_type text null,
  optimal_score integer null,
  source_utc_offset integer null,
  location_lon double precision null,
  location_lat double precision null,
  run_init_ts timestamptz null,
  source_raw_key text not null,
  schema_version integer not null default 1,
  created_at timestamptz not null default now(),

  constraint forecast_fact_wind_pk unique (forecast_run_id, spot_id, forecast_ts)
);

create table if not exists forecast_fact_tides (
  forecast_run_id text not null,
  spot_id text not null,
  spot_version_id text not null,
  forecast_ts timestamptz not null,
  tide_index integer not null,
  scraped_at timestamptz not null,
  scheduled_utc_time timestamptz not null,
  utc_offset integer null,
  timezone text null,
  tide_type text null,
  height double precision null,
  source_utc_offset integer null,
  tide_location_name text null,
  tide_location_lon double precision null,
  tide_location_lat double precision null,
  tide_location_min double precision null,
  tide_location_max double precision null,
  tide_location_mean double precision null,
  source_raw_key text not null,
  schema_version integer not null default 1,
  created_at timestamptz not null default now(),

  constraint forecast_fact_tides_pk unique (forecast_run_id, spot_id, forecast_ts, tide_index)
);

create index if not exists forecast_fact_rating_spot_forecast_ts_idx
  on forecast_fact_rating (spot_id, forecast_ts);
create index if not exists forecast_fact_rating_scraped_at_idx
  on forecast_fact_rating (scraped_at);
create index if not exists forecast_fact_rating_run_idx
  on forecast_fact_rating (forecast_run_id);

create index if not exists forecast_fact_wave_spot_forecast_ts_idx
  on forecast_fact_wave (spot_id, forecast_ts);
create index if not exists forecast_fact_wave_scraped_at_idx
  on forecast_fact_wave (scraped_at);
create index if not exists forecast_fact_wave_run_idx
  on forecast_fact_wave (forecast_run_id);

create index if not exists forecast_fact_swells_spot_forecast_ts_idx
  on forecast_fact_swells (spot_id, forecast_ts);
create index if not exists forecast_fact_swells_scraped_at_idx
  on forecast_fact_swells (scraped_at);
create index if not exists forecast_fact_swells_run_idx
  on forecast_fact_swells (forecast_run_id);

create index if not exists forecast_fact_wind_spot_forecast_ts_idx
  on forecast_fact_wind (spot_id, forecast_ts);
create index if not exists forecast_fact_wind_scraped_at_idx
  on forecast_fact_wind (scraped_at);
create index if not exists forecast_fact_wind_run_idx
  on forecast_fact_wind (forecast_run_id);

create index if not exists forecast_fact_tides_spot_forecast_ts_idx
  on forecast_fact_tides (spot_id, forecast_ts);
create index if not exists forecast_fact_tides_scraped_at_idx
  on forecast_fact_tides (scraped_at);
create index if not exists forecast_fact_tides_run_idx
  on forecast_fact_tides (forecast_run_id);
