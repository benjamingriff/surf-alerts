-- Partitioned forecast hot-store schema for fresh RDS deployments.
-- Assumes no existing forecast fact tables. Historical non-partitioned schema is kept in 0002.

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

  constraint forecast_fact_rating_pk unique (scheduled_utc_time, forecast_run_id, spot_id, forecast_ts)
) partition by range (scheduled_utc_time);

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

  constraint forecast_fact_wave_pk unique (scheduled_utc_time, forecast_run_id, spot_id, forecast_ts)
) partition by range (scheduled_utc_time);

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

  constraint forecast_fact_swells_pk unique (scheduled_utc_time, forecast_run_id, spot_id, forecast_ts, swell_index)
) partition by range (scheduled_utc_time);

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

  constraint forecast_fact_wind_pk unique (scheduled_utc_time, forecast_run_id, spot_id, forecast_ts)
) partition by range (scheduled_utc_time);

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

  constraint forecast_fact_tides_pk unique (scheduled_utc_time, forecast_run_id, spot_id, forecast_ts, tide_index)
) partition by range (scheduled_utc_time);

create table if not exists forecast_fact_rating_default partition of forecast_fact_rating default;
create table if not exists forecast_fact_wave_default partition of forecast_fact_wave default;
create table if not exists forecast_fact_swells_default partition of forecast_fact_swells default;
create table if not exists forecast_fact_wind_default partition of forecast_fact_wind default;
create table if not exists forecast_fact_tides_default partition of forecast_fact_tides default;

create index if not exists forecast_fact_rating_spot_scheduled_forecast_ts_idx
  on forecast_fact_rating (spot_id, scheduled_utc_time, forecast_ts);
create index if not exists forecast_fact_rating_run_idx
  on forecast_fact_rating (forecast_run_id);

create index if not exists forecast_fact_wave_spot_scheduled_forecast_ts_idx
  on forecast_fact_wave (spot_id, scheduled_utc_time, forecast_ts);
create index if not exists forecast_fact_wave_run_idx
  on forecast_fact_wave (forecast_run_id);

create index if not exists forecast_fact_swells_spot_scheduled_forecast_ts_idx
  on forecast_fact_swells (spot_id, scheduled_utc_time, forecast_ts);
create index if not exists forecast_fact_swells_run_idx
  on forecast_fact_swells (forecast_run_id);

create index if not exists forecast_fact_wind_spot_scheduled_forecast_ts_idx
  on forecast_fact_wind (spot_id, scheduled_utc_time, forecast_ts);
create index if not exists forecast_fact_wind_run_idx
  on forecast_fact_wind (forecast_run_id);

create index if not exists forecast_fact_tides_spot_scheduled_forecast_ts_idx
  on forecast_fact_tides (spot_id, scheduled_utc_time, forecast_ts);
create index if not exists forecast_fact_tides_run_idx
  on forecast_fact_tides (forecast_run_id);


do $$
declare
  partition_day date;
  table_name text;
  partition_name text;
  table_names text[] := array[
    'forecast_fact_rating',
    'forecast_fact_wave',
    'forecast_fact_swells',
    'forecast_fact_wind',
    'forecast_fact_tides'
  ];
begin
  foreach table_name in array table_names loop
    for partition_day in
      select generate_series(
        (now() at time zone 'utc')::date,
        (now() at time zone 'utc')::date + 4,
        interval '1 day'
      )::date
    loop
      partition_name := format('%s_%s', table_name, to_char(partition_day, 'YYYYMMDD'));
      execute format(
        'create table if not exists %I partition of %I for values from (%L) to (%L)',
        partition_name,
        table_name,
        partition_day::timestamptz,
        (partition_day + 1)::timestamptz
      );
    end loop;
  end loop;
end $$;
