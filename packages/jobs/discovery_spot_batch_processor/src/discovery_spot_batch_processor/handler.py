import gzip
import json
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any

import boto3
from discovery_control import (
    ControlStore,
    RUN_STATUS_COMPLETE,
    RUN_STATUS_SPOT_PROCESSING,
    RUN_STATUS_SPOT_PROCESSING_QUEUED,
    SPOT_STATUS_SUCCESS,
)
from discovery_spot_model import (
    build_added_spot_version_row,
    build_removed_tombstone_row,
    canonicalize_spot_report,
)
from postgres_client import connect

COLUMNS = [
    "spot_version_id",
    "spot_id",
    "event_type",
    "is_current",
    "valid_from",
    "valid_to",
    "content_checksum",
    "name",
    "lat",
    "lon",
    "timezone",
    "utc_offset",
    "abbr_timezone",
    "href",
    "breadcrumbs",
    "subregion",
    "travel_details",
    "source_run_id",
    "source_raw_key",
    "source_type",
    "schema_version",
]
JSON_COLUMNS = {"breadcrumbs", "subregion", "travel_details"}
DEFAULT_S3_READ_WORKERS = 16


def _s3_client():
    return boto3.client("s3")


def _store() -> ControlStore:
    return ControlStore()


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _s3_read_workers() -> int:
    return int(os.environ.get("DISCOVERY_SPOT_BATCH_S3_READ_WORKERS", DEFAULT_S3_READ_WORKERS))


def _get_json(bucket: str, key: str) -> dict[str, Any]:
    data = _s3_client().get_object(Bucket=bucket, Key=key)["Body"].read()
    if key.endswith(".gz"):
        data = gzip.decompress(data)
    return json.loads(data)


def serialize_row_values(row: dict[str, Any]) -> list[Any]:
    values = []
    for column in COLUMNS:
        value = row.get(column)
        if column in JSON_COLUMNS and value is not None:
            value = json.dumps(value)
        values.append(value)
    return values


def _chunks(items: list[Any], size: int):
    for start in range(0, len(items), size):
        yield items[start : start + size]


def _insert_rows(cur, rows: list[dict[str, Any]], batch_size: int = 1000) -> None:
    if not rows:
        return

    sql = f"insert into discovery_spot_versions ({','.join(COLUMNS)}) values ({','.join(['%s'] * len(COLUMNS))}) on conflict (spot_version_id) do nothing"
    for chunk in _chunks(rows, batch_size):
        cur.executemany(sql, [serialize_row_values(row) for row in chunk])


def build_added_row(
    *, bucket: str, run_id: str, item: dict[str, Any], valid_from: str
) -> dict[str, Any]:
    raw = _get_json(item.get("raw_bucket") or bucket, item["raw_key"])
    canonical = canonicalize_spot_report(raw, item["spot_id"])
    return build_added_spot_version_row(
        canonical_spot=canonical,
        discovery_run_id=run_id,
        source_raw_key=item["raw_key"],
        valid_from=valid_from,
    )


def build_added_rows(
    *,
    bucket: str,
    run_id: str,
    success_items: list[dict[str, Any]],
    valid_from: str,
    max_workers: int | None = None,
) -> list[dict[str, Any]]:
    if not success_items:
        return []

    workers = max_workers or _s3_read_workers()
    with ThreadPoolExecutor(max_workers=workers) as executor:
        return list(
            executor.map(
                lambda item: build_added_row(
                    bucket=bucket,
                    run_id=run_id,
                    item=item,
                    valid_from=valid_from,
                ),
                success_items,
            )
        )


def _fetch_current_removed_rows(cur, spot_ids: list[str]) -> dict[str, dict[str, Any]]:
    if not spot_ids:
        return {}
    cur.execute(
        "select * from discovery_spot_versions where is_current = true and event_type <> 'removed' and spot_id = any(%s)",
        (spot_ids,),
    )
    return {row["spot_id"]: row for row in cur.fetchall()}


def _fetch_current_added_rows(cur, spot_ids: list[str]) -> dict[str, dict[str, Any]]:
    if not spot_ids:
        return {}
    cur.execute(
        "select spot_id, spot_version_id, content_checksum, event_type from discovery_spot_versions where is_current = true and spot_id = any(%s)",
        (spot_ids,),
    )
    return {row["spot_id"]: row for row in cur.fetchall()}


def _plan_added_rows(
    *, added_rows: list[dict[str, Any]], current_by_spot: dict[str, dict[str, Any]]
) -> tuple[list[dict[str, Any]], list[str]]:
    rows_to_insert = []
    readded_spot_ids = []
    conflicts = []

    for row in added_rows:
        current = current_by_spot.get(row["spot_id"])
        if not current:
            rows_to_insert.append(row)
        elif current.get("event_type") == "removed":
            readded_spot_ids.append(row["spot_id"])
            rows_to_insert.append(row)
        elif current["spot_version_id"] != row["spot_version_id"]:
            conflicts.append(row["spot_id"])

    if len(conflicts) == 1:
        raise RuntimeError(f"Current active spot conflict for {conflicts[0]}")
    if conflicts:
        raise RuntimeError(f"Current active spot conflicts: {conflicts[:20]}")

    return rows_to_insert, readded_spot_ids


def _close_current_rows(cur, *, valid_from: str, spot_ids: list[str]) -> None:
    if not spot_ids:
        return
    cur.execute(
        "update discovery_spot_versions set is_current=false, valid_to=%s where spot_id = any(%s) and is_current=true",
        (valid_from, spot_ids),
    )


def _close_current_removed_tombstones(cur, *, valid_from: str, spot_ids: list[str]) -> None:
    if not spot_ids:
        return
    cur.execute(
        "update discovery_spot_versions set is_current=false, valid_to=%s where spot_id = any(%s) and is_current=true and event_type='removed'",
        (valid_from, spot_ids),
    )


def apply_spot_version_changes(
    *,
    conn,
    run_id: str,
    manifest: dict[str, Any],
    added_rows: list[dict[str, Any]],
    valid_from: str,
) -> None:
    removed_spot_ids = manifest["removed_spot_ids"]
    added_spot_ids = [row["spot_id"] for row in added_rows]

    with conn.transaction():
        with conn.cursor() as cur:
            current_removed = _fetch_current_removed_rows(cur, removed_spot_ids)
            current_added = _fetch_current_added_rows(cur, added_spot_ids)
            rows_to_insert, readded_spot_ids = _plan_added_rows(
                added_rows=added_rows, current_by_spot=current_added
            )
            tombstone_rows = [
                build_removed_tombstone_row(
                    current_row=current,
                    discovery_run_id=run_id,
                    source_raw_key=manifest["sitemap_raw_key"],
                    valid_from=valid_from,
                )
                for current in current_removed.values()
            ]

            _close_current_rows(cur, valid_from=valid_from, spot_ids=list(current_removed))
            _close_current_removed_tombstones(cur, valid_from=valid_from, spot_ids=readded_spot_ids)
            _insert_rows(cur, tombstone_rows)
            _insert_rows(cur, rows_to_insert)


def should_process_run(run_id: str, store: ControlStore) -> str:
    run = store.get_run(run_id)
    if not run:
        return "missing_run"

    status = run.get("status")

    if status == RUN_STATUS_COMPLETE:
        return "already_complete"

    if status == RUN_STATUS_SPOT_PROCESSING:
        return "process"

    if status == RUN_STATUS_SPOT_PROCESSING_QUEUED:
        claimed = store.transition_run_status(
            discovery_run_id=run_id,
            from_status=RUN_STATUS_SPOT_PROCESSING_QUEUED,
            to_status=RUN_STATUS_SPOT_PROCESSING,
        )
        return "process" if claimed else "claim_lost"

    return f"invalid_status:{status}"


def process_discovery_run(run_id: str, *, store: ControlStore | None = None) -> str:
    store = store or _store()
    run = store.get_run(run_id)
    if not run:
        return "missing_run"
    if run.get("status") == RUN_STATUS_COMPLETE:
        return "already_complete"

    bucket = os.environ["DATA_BUCKET"]
    valid_from = _utc_now_iso()
    manifest = _get_json(bucket, run["planner_manifest_key"])
    success_items = store.list_spots(run_id, terminal_status=SPOT_STATUS_SUCCESS)
    expected_success_count = run.get("success_scrape_count")
    if expected_success_count is not None and len(success_items) != int(expected_success_count):
        raise RuntimeError(
            f"Success spot count mismatch for {run_id}: "
            f"loaded {len(success_items)} successful spots, "
            f"expected {expected_success_count} from run summary"
        )

    added_rows = build_added_rows(
        bucket=bucket, run_id=run_id, success_items=success_items, valid_from=valid_from
    )
    if len(added_rows) != len(success_items):
        raise RuntimeError(
            f"Added row count mismatch for {run_id}: "
            f"built {len(added_rows)} rows from {len(success_items)} successful spots"
        )

    with connect(os.environ["SUPABASE_POSTGRES_URL_PARAMETER_NAME"]) as conn:
        apply_spot_version_changes(
            conn=conn,
            run_id=run_id,
            manifest=manifest,
            added_rows=added_rows,
            valid_from=valid_from,
        )
    store.mark_complete(run_id)
    return "processed"


def lambda_handler(event, context):
    store = _store()
    results = []
    for record in event["Records"]:
        run_id = json.loads(record["body"])["discovery_run_id"]
        decision = should_process_run(run_id, store)

        if decision == "process":
            results.append(process_discovery_run(run_id, store=store))
        else:
            results.append(decision)
    return {"statusCode": 200, "body": json.dumps({"results": results})}
