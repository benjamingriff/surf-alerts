import gzip
import json
import os
from datetime import datetime, timezone
from typing import Any

import boto3
from discovery_control import (
    ControlStore,
    RUN_STATUS_NO_OP_COMPLETE,
    RUN_STATUS_WAITING_FOR_SPOT_SCRAPES,
)
from postgres_client import connect

RUN_STATUS_SPOT_SCRAPES_COMPLETE = "spot_scrapes_complete"
SCHEMA_VERSION = 1


def _s3():
    return boto3.client("s3")


def _sqs():
    return boto3.client("sqs")


def _store() -> ControlStore:
    return ControlStore()


def classify_spots(sitemap_spot_ids: set[str], current_active_spot_ids: set[str]) -> dict[str, Any]:
    added = sorted(sitemap_spot_ids - current_active_spot_ids)
    removed = sorted(current_active_spot_ids - sitemap_spot_ids)
    existing = sitemap_spot_ids & current_active_spot_ids
    return {
        "added_spot_ids": added,
        "removed_spot_ids": removed,
        "existing_spot_count": len(existing),
        "added_count": len(added),
        "removed_count": len(removed),
    }


def build_planner_manifest(
    *,
    discovery_run_id: str,
    scrape_date: str,
    raw_bucket: str,
    raw_key: str,
    classification: dict[str, Any],
    planned_at: str,
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "discovery_run_id": discovery_run_id,
        "scrape_date": scrape_date,
        "sitemap_raw_bucket": raw_bucket,
        "sitemap_raw_key": raw_key,
        "planned_at": planned_at,
        **classification,
    }


def _manifest_key(discovery_run_id: str) -> str:
    return f"control/discovery/planner_manifest/discovery_run_id={discovery_run_id}.json"


def _get_json(bucket: str, key: str) -> dict:
    data = _s3().get_object(Bucket=bucket, Key=key)["Body"].read()
    if key.endswith(".gz"):
        data = gzip.decompress(data)
    return json.loads(data)


def _put_json(bucket: str, key: str, body: dict) -> None:
    _s3().put_object(
        Bucket=bucket, Key=key, Body=json.dumps(body).encode(), ContentType="application/json"
    )


def _current_active_ids() -> set[str]:
    with connect(os.environ["SUPABASE_POSTGRES_URL_PARAMETER_NAME"]) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "select spot_id from discovery_spot_versions where is_current = true and event_type <> 'removed'"
            )
            return {r["spot_id"] for r in cur.fetchall()}


def _queue_spot_scrapes(
    *,
    queue_url: str,
    discovery_run_id: str,
    scrape_date: str,
    raw_key: str,
    spot_ids: list[str],
    requested_at: str,
) -> None:
    for spot_id in spot_ids:
        _sqs().send_message(
            QueueUrl=queue_url,
            MessageBody=json.dumps(
                {
                    "schema_version": SCHEMA_VERSION,
                    "message_type": "spot_scrape_requested",
                    "discovery_run_id": discovery_run_id,
                    "scrape_date": scrape_date,
                    "spot_id": spot_id,
                    "sitemap_raw_key": raw_key,
                    "requested_at": requested_at,
                }
            ),
        )


def _queue_batch_processor(*, discovery_run_id: str, requested_at: str) -> None:
    _sqs().send_message(
        QueueUrl=os.environ["DISCOVERY_SPOT_BATCH_PROCESSOR_QUEUE_URL"],
        MessageBody=json.dumps(
            {
                "schema_version": SCHEMA_VERSION,
                "message_type": "discovery_spot_batch_process_requested",
                "discovery_run_id": discovery_run_id,
                "requested_at": requested_at,
            }
        ),
    )


def process_sitemap_completion(message: dict[str, Any]) -> str:
    discovery_run_id = message["discovery_run_id"]
    scrape_date = message["scrape_date"]
    raw_bucket = message["raw_bucket"]
    raw_key = message["raw_key"]
    store = _store()

    if not store.create_run_if_absent(
        discovery_run_id=discovery_run_id, scrape_date=scrape_date, sitemap_raw_key=raw_key
    ):
        return "duplicate"

    sitemap = _get_json(raw_bucket, raw_key)
    classification = classify_spots(set(sitemap.get("spots", [])), _current_active_ids())
    planned_at = datetime.now(timezone.utc).isoformat()
    manifest_key = _manifest_key(discovery_run_id)
    manifest = build_planner_manifest(
        discovery_run_id=discovery_run_id,
        scrape_date=scrape_date,
        raw_bucket=raw_bucket,
        raw_key=raw_key,
        classification=classification,
        planned_at=planned_at,
    )
    _put_json(os.environ["DATA_BUCKET"], manifest_key, manifest)

    added = classification["added_spot_ids"]
    removed = classification["removed_spot_ids"]
    if not added and not removed:
        store.update_run_plan(
            discovery_run_id=discovery_run_id,
            planner_manifest_key=manifest_key,
            expected_spot_count=0,
            added_count=0,
            removed_count=0,
            existing_spot_count=classification["existing_spot_count"],
            status=RUN_STATUS_NO_OP_COMPLETE,
        )
        return "no_op"

    store.update_run_plan(
        discovery_run_id=discovery_run_id,
        planner_manifest_key=manifest_key,
        expected_spot_count=len(added),
        added_count=len(added),
        removed_count=len(removed),
        existing_spot_count=classification["existing_spot_count"],
        status=RUN_STATUS_WAITING_FOR_SPOT_SCRAPES if added else RUN_STATUS_SPOT_SCRAPES_COMPLETE,
    )
    store.seed_spots(discovery_run_id=discovery_run_id, spot_ids=added)

    if added:
        _queue_spot_scrapes(
            queue_url=os.environ["SPOT_SCRAPER_QUEUE_URL"],
            discovery_run_id=discovery_run_id,
            scrape_date=scrape_date,
            raw_key=raw_key,
            spot_ids=added,
            requested_at=planned_at,
        )
    elif removed:
        _queue_batch_processor(discovery_run_id=discovery_run_id, requested_at=planned_at)

    return "planned"


def lambda_handler(event, context):
    results = [
        process_sitemap_completion(json.loads(record["body"])) for record in event["Records"]
    ]
    return {"statusCode": 200, "body": json.dumps({"results": results})}
