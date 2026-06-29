from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

FORECAST_FACT_TABLES: tuple[str, ...] = (
    "forecast_fact_rating",
    "forecast_fact_wave",
    "forecast_fact_swells",
    "forecast_fact_wind",
    "forecast_fact_tides",
)


class DefaultPartitionNotEmptyError(RuntimeError):
    """Raised when rows landed in a default partition."""


@dataclass(frozen=True)
class PartitionSpec:
    parent_table: str
    partition_day: date

    @property
    def partition_name(self) -> str:
        return f"{self.parent_table}_{self.partition_day:%Y%m%d}"

    @property
    def start_timestamp(self) -> str:
        return f"{self.partition_day.isoformat()} 00:00:00+00"

    @property
    def end_timestamp(self) -> str:
        return f"{(self.partition_day + timedelta(days=1)).isoformat()} 00:00:00+00"


def utc_today(now: datetime | None = None) -> date:
    value = now or datetime.now(UTC)
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).date()


def partitions_to_create(
    today: date, *, days_ahead: int = 4, tables: tuple[str, ...] = FORECAST_FACT_TABLES
) -> list[PartitionSpec]:
    return [
        PartitionSpec(table, today + timedelta(days=offset))
        for table in tables
        for offset in range(days_ahead + 1)
    ]


def retention_cutoff(today: date, *, retention_days: int = 3) -> date:
    return today - timedelta(days=retention_days - 1)


def partition_create_sql(spec: PartitionSpec) -> str:
    return (
        f'create table if not exists "{spec.partition_name}" '
        f'partition of "{spec.parent_table}" '
        f"for values from ('{spec.start_timestamp}') to ('{spec.end_timestamp}')"
    )


def partition_drop_sql(partition_name: str) -> str:
    return f'drop table if exists "{partition_name}"'


def default_partition_name(parent_table: str) -> str:
    return f"{parent_table}_default"


def discover_partitions_sql() -> str:
    quoted_tables = ", ".join(f"'{table}'" for table in FORECAST_FACT_TABLES)
    return f"""
select
  parent.relname as parent_table,
  child.relname as partition_name
from pg_inherits
join pg_class parent on pg_inherits.inhparent = parent.oid
join pg_class child on pg_inherits.inhrelid = child.oid
where parent.relname in ({quoted_tables})
""".strip()


def extract_partition_day(parent_table: str, partition_name: str) -> date | None:
    prefix = f"{parent_table}_"
    if not partition_name.startswith(prefix) or partition_name.endswith("_default"):
        return None
    suffix = partition_name.removeprefix(prefix)
    if len(suffix) != 8 or not suffix.isdigit():
        return None
    return date(int(suffix[:4]), int(suffix[4:6]), int(suffix[6:8]))


def select_partitions_to_drop(rows: list[dict], cutoff: date) -> list[str]:
    selected: list[str] = []
    for row in rows:
        day = extract_partition_day(row["parent_table"], row["partition_name"])
        if day is not None and day < cutoff:
            selected.append(row["partition_name"])
    return selected


def default_partition_count_sql(default_partition: str) -> str:
    return f'select count(*) as row_count from "{default_partition}"'


def maintain_partitions(conn, *, now: datetime | None = None) -> dict[str, int]:
    today = utc_today(now)
    created = partitions_to_create(today)
    for spec in created:
        conn.execute(partition_create_sql(spec))

    existing = list(conn.execute(discover_partitions_sql()))
    to_drop = select_partitions_to_drop(existing, retention_cutoff(today))
    for partition_name in to_drop:
        conn.execute(partition_drop_sql(partition_name))

    default_counts: dict[str, int] = {}
    for table in FORECAST_FACT_TABLES:
        name = default_partition_name(table)
        row = conn.execute(default_partition_count_sql(name)).fetchone()
        count = int(row["row_count"] if isinstance(row, dict) else row[0])
        default_counts[name] = count

    offenders = {name: count for name, count in default_counts.items() if count > 0}
    if offenders:
        raise DefaultPartitionNotEmptyError(f"Forecast default partitions contain rows: {offenders}")

    conn.commit()
    return {"created_or_existing": len(created), "dropped": len(to_drop), "defaults_checked": len(default_counts)}
