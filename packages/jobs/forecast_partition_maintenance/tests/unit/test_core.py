from datetime import UTC, date, datetime

import pytest

from forecast_partition_maintenance.core import (
    DefaultPartitionNotEmptyError,
    PartitionSpec,
    extract_partition_day,
    maintain_partitions,
    partition_create_sql,
    partitions_to_create,
    retention_cutoff,
    select_partitions_to_drop,
)


def test_partition_sql_generation_is_deterministic():
    spec = PartitionSpec("forecast_fact_wave", date(2026, 5, 29))

    assert spec.partition_name == "forecast_fact_wave_20260529"
    assert partition_create_sql(spec) == (
        'create table if not exists "forecast_fact_wave_20260529" '
        'partition of "forecast_fact_wave" '
        "for values from ('2026-05-29 00:00:00+00') to ('2026-05-30 00:00:00+00')"
    )


def test_partitions_to_create_includes_today_through_four_days_ahead_for_each_table():
    specs = partitions_to_create(date(2026, 5, 29), tables=("forecast_fact_rating",))

    assert [spec.partition_name for spec in specs] == [
        "forecast_fact_rating_20260529",
        "forecast_fact_rating_20260530",
        "forecast_fact_rating_20260531",
        "forecast_fact_rating_20260601",
        "forecast_fact_rating_20260602",
    ]


def test_retention_cutoff_keeps_three_daily_partitions():
    assert retention_cutoff(date(2026, 5, 29)) == date(2026, 5, 27)


def test_select_partitions_to_drop_only_drops_partitions_older_than_cutoff():
    rows = [
        {"parent_table": "forecast_fact_rating", "partition_name": "forecast_fact_rating_20260526"},
        {"parent_table": "forecast_fact_rating", "partition_name": "forecast_fact_rating_20260527"},
        {"parent_table": "forecast_fact_rating", "partition_name": "forecast_fact_rating_default"},
        {"parent_table": "forecast_fact_wave", "partition_name": "unrecognised"},
    ]

    assert select_partitions_to_drop(rows, date(2026, 5, 27)) == [
        "forecast_fact_rating_20260526"
    ]


def test_extract_partition_day_ignores_default_and_invalid_names():
    assert extract_partition_day("forecast_fact_wave", "forecast_fact_wave_20260529") == date(
        2026, 5, 29
    )
    assert extract_partition_day("forecast_fact_wave", "forecast_fact_wave_default") is None
    assert extract_partition_day("forecast_fact_wave", "forecast_fact_wave_recent") is None


class FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def __iter__(self):
        return iter(self._rows)

    def fetchone(self):
        return self._rows[0]


class FakeConnection:
    def __init__(self, default_count=0):
        self.sql: list[str] = []
        self.default_count = default_count
        self.committed = False

    def execute(self, sql):
        self.sql.append(sql)
        if "from pg_inherits" in sql:
            return FakeResult(
                [
                    {
                        "parent_table": "forecast_fact_rating",
                        "partition_name": "forecast_fact_rating_20260526",
                    },
                    {
                        "parent_table": "forecast_fact_rating",
                        "partition_name": "forecast_fact_rating_20260527",
                    },
                ]
            )
        if "count(*) as row_count" in sql:
            return FakeResult([{"row_count": self.default_count}])
        return FakeResult([])

    def commit(self):
        self.committed = True


def test_maintain_partitions_creates_future_partitions_drops_old_partitions_and_commits():
    conn = FakeConnection()

    result = maintain_partitions(conn, now=datetime(2026, 5, 29, 12, tzinfo=UTC))

    assert result == {"created_or_existing": 25, "dropped": 1, "defaults_checked": 5}
    assert 'create table if not exists "forecast_fact_rating_20260529"' in conn.sql[0]
    assert 'drop table if exists "forecast_fact_rating_20260526"' in conn.sql
    assert conn.committed is True


def test_maintain_partitions_fails_when_default_partition_contains_rows():
    conn = FakeConnection(default_count=2)

    with pytest.raises(DefaultPartitionNotEmptyError, match="default partitions contain rows"):
        maintain_partitions(conn, now=datetime(2026, 5, 29, 12, tzinfo=UTC))

    assert conn.committed is False
