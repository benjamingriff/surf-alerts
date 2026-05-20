import gzip
import json
import os
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
    "subregion_id",
    "subregion_name",
    "sitemap_link",
    "forecast_link",
    "breadcrumbs",
    "cameras",
    "ability_levels",
    "board_types",
    "travel_details",
    "source_run_id",
    "source_raw_key",
    "source_type",
    "schema_version",
]
JSON_COLUMNS = {"breadcrumbs", "cameras", "ability_levels", "board_types", "travel_details"}


def _s3_client():
    return boto3.client("s3")


def _store() -> ControlStore:
    return ControlStore()


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


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


def _insert_row(cur, row: dict[str, Any]) -> None:
    cur.execute(
        f"insert into discovery_spot_versions ({','.join(COLUMNS)}) values ({','.join(['%s'] * len(COLUMNS))}) on conflict (spot_version_id) do nothing",
        serialize_row_values(row),
    )


def build_added_rows(
    *, bucket: str, run_id: str, success_items: list[dict[str, Any]], valid_from: str
) -> list[dict[str, Any]]:
    rows = []
    for item in success_items:
        raw = _get_json(item.get("raw_bucket") or bucket, item["raw_key"])
        canonical = canonicalize_spot_report(raw, item["spot_id"])
        rows.append(
            build_added_spot_version_row(
                canonical_spot=canonical,
                discovery_run_id=run_id,
                source_raw_key=item["raw_key"],
                valid_from=valid_from,
            )
        )
    return rows


def apply_spot_version_changes(
    *,
    conn,
    run_id: str,
    manifest: dict[str, Any],
    added_rows: list[dict[str, Any]],
    valid_from: str,
) -> None:
    with conn.transaction():
        with conn.cursor() as cur:
            cur.execute(
                "select * from discovery_spot_versions where is_current = true and event_type <> 'removed' and spot_id = any(%s)",
                (manifest["removed_spot_ids"],),
            )
            current_removed = {row["spot_id"]: row for row in cur.fetchall()}
            for spot_id, current in current_removed.items():
                tombstone = build_removed_tombstone_row(
                    current_row=current,
                    discovery_run_id=run_id,
                    source_raw_key=manifest["sitemap_raw_key"],
                    valid_from=valid_from,
                )
                cur.execute(
                    "update discovery_spot_versions set is_current=false, valid_to=%s where spot_id=%s and is_current=true",
                    (valid_from, spot_id),
                )
                _insert_row(cur, tombstone)

            for row in added_rows:
                cur.execute(
                    "select spot_version_id, content_checksum, event_type from discovery_spot_versions where spot_id=%s and is_current=true",
                    (row["spot_id"],),
                )
                existing = cur.fetchone()

                if existing:
                    if existing.get("event_type") != "removed":
                        if existing["spot_version_id"] == row["spot_version_id"]:
                            continue
                        raise RuntimeError(f"Current active spot conflict for {row['spot_id']}")

                    cur.execute(
                        "update discovery_spot_versions set is_current=false, valid_to=%s where spot_id=%s and is_current=true",
                        (valid_from, row["spot_id"]),
                    )

                _insert_row(cur, row)


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
    added_rows = build_added_rows(
        bucket=bucket, run_id=run_id, success_items=success_items, valid_from=valid_from
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
