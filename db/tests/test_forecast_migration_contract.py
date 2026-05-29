from __future__ import annotations

import re
from pathlib import Path

from forecast_spot_processor.handler import CONFLICT_TARGETS, TABLE_COLUMNS


MIGRATION = Path(__file__).parents[1] / "migrations" / "0003_create_partitioned_forecast_tables.sql"
ACTIVE_TABLES = {
    "forecast_fact_rating",
    "forecast_fact_wave",
    "forecast_fact_swells",
    "forecast_fact_wind",
    "forecast_fact_tides",
}
COMMON_LINEAGE_COLUMNS = {
    "forecast_run_id",
    "spot_id",
    "spot_version_id",
    "forecast_ts",
    "scraped_at",
    "scheduled_utc_time",
    "utc_offset",
    "timezone",
    "source_raw_key",
    "schema_version",
    "created_at",
}


def _sql() -> str:
    return MIGRATION.read_text()


def _created_parent_tables(sql: str) -> set[str]:
    return set(
        re.findall(
            r"create table if not exists\s+(forecast_\w+)\s*\(", sql, flags=re.I
        )
    )


def _table_body(sql: str, table: str) -> str:
    match = re.search(
        rf"create table if not exists\s+{table}\s*\((.*?)\n\)\s+partition by range\s*\(scheduled_utc_time\);",
        sql,
        flags=re.I | re.S,
    )
    assert match, f"missing create table statement for {table}"
    return match.group(1)


def _columns(sql: str, table: str) -> set[str]:
    body = _table_body(sql, table)
    columns = set()
    for raw_line in body.splitlines():
        line = raw_line.strip()
        if not line or line.lower().startswith("constraint"):
            continue
        columns.add(line.split()[0])
    return columns


def test_migration_creates_only_active_v1_forecast_fact_parent_tables():
    tables = _created_parent_tables(_sql())

    assert tables == ACTIVE_TABLES
    assert all("weather" not in table and "sunlight" not in table for table in tables)


def test_migration_tables_include_processor_insert_columns_and_common_lineage():
    sql = _sql()

    for table, insert_columns in TABLE_COLUMNS.items():
        migration_columns = _columns(sql, table)
        assert set(insert_columns).issubset(migration_columns), table
        assert COMMON_LINEAGE_COLUMNS.issubset(migration_columns), table


def test_unique_constraints_match_processor_on_conflict_targets():
    sql = _sql()

    for table, target in CONFLICT_TARGETS.items():
        normalized_target = ", ".join(part.strip() for part in target.split(","))
        body = _table_body(sql, table)
        assert f"unique ({normalized_target})" in body
        assert "spot_version_id" not in normalized_target


def test_swells_and_tides_uniqueness_preserves_source_ordinals():
    assert CONFLICT_TARGETS["forecast_fact_swells"] == (
        "scheduled_utc_time, forecast_run_id, spot_id, forecast_ts, swell_index"
    )
    assert CONFLICT_TARGETS["forecast_fact_tides"] == (
        "scheduled_utc_time, forecast_run_id, spot_id, forecast_ts, tide_index"
    )


def test_every_forecast_parent_table_is_range_partitioned_by_scheduled_utc_time():
    sql = _sql()

    for table in ACTIVE_TABLES:
        assert re.search(
            rf"create table if not exists\s+{table}\s*\(.*?\)\s+partition by range\s*\(scheduled_utc_time\)",
            sql,
            flags=re.I | re.S,
        ), table


def test_every_forecast_table_has_default_partition_and_initial_partition_block():
    sql = _sql()

    for table in ACTIVE_TABLES:
        assert re.search(
            rf"create table if not exists\s+{table}_default\s+partition of\s+{table}\s+default",
            sql,
            flags=re.I,
        ), table
    assert "generate_series" in sql
    assert "(now() at time zone 'utc')::date + 4" in sql


def test_indexes_support_spot_time_and_run_lookup_without_scraped_at_indexes():
    sql = _sql()

    for table in ACTIVE_TABLES:
        assert re.search(
            rf"create index if not exists\s+{table}_spot_scheduled_forecast_ts_idx\s+on\s+{table}\s*\(spot_id, scheduled_utc_time, forecast_ts\)",
            sql,
            flags=re.I,
        ), table
        assert re.search(
            rf"create index if not exists\s+{table}_run_idx\s+on\s+{table}\s*\(forecast_run_id\)",
            sql,
            flags=re.I,
        ), table
        assert f"{table}_scraped_at_idx" not in sql
