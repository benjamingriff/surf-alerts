import json
import os
from datetime import datetime, timezone
from urllib.parse import unquote_plus
from uuid import uuid4

import boto3
from aws_lambda_powertools.utilities.typing import LambdaContext

from discovery_diff.logger import get_logger, inject_lambda_context
from discovery_diff.s3 import S3Client

logger = get_logger()
s3_client = S3Client()
sqs_client = boto3.client("sqs")

CATALOG_CORE_KEY = "processed/discovery/catalog_latest/dim_spots_core.parquet"
SCHEMA_VERSION = 1


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_s3_reference(event: dict) -> tuple[str, str]:
    if "detail" in event:
        bucket = event["detail"]["bucket"]["name"]
        key = unquote_plus(event["detail"]["object"]["key"])
        return bucket, key

    record = event["Records"][0]
    bucket = record["s3"]["bucket"]["name"]
    key = unquote_plus(record["s3"]["object"]["key"])
    return bucket, key


def _discovery_manifest_key(scrape_date: str, discovery_run_id: str) -> str:
    return (
        "control/manifests/discovery_runs/"
        f"date={scrape_date}/discovery_run_id={discovery_run_id}/manifest.json.gz"
    )


def _processing_manifest_key(scrape_date: str, discovery_run_id: str, stage: str) -> str:
    return (
        "control/manifests/processing/"
        f"domain=discovery/stage={stage}/date={scrape_date}/discovery_run_id={discovery_run_id}.json.gz"
    )


def _events_key(event_ts: datetime) -> str:
    return (
        "processed/discovery/events/"
        f"year={event_ts:%Y}/month={event_ts:%m}/event_date={event_ts:%Y-%m-%d}/"
        f"part-{uuid4()}.parquet"
    )


def _core_key(version_ts: datetime) -> str:
    return (
        "processed/discovery/dim_spots_core/"
        f"year={version_ts:%Y}/month={version_ts:%m}/part-{uuid4()}.parquet"
    )


def _build_added_event(spot_id: str, raw_key: str, discovery_run_id: str, event_ts: datetime) -> dict:
    return {
        "event_ts": event_ts,
        "run_id": discovery_run_id,
        "spot_id": spot_id,
        "event_type": "added",
        "source_type": "sitemap",
        "source_raw_key": raw_key,
        "old_checksum": None,
        "new_checksum": None,
        "spot_version_id": None,
        "version_ts": None,
    }


def _build_removed_rows(
    *,
    latest_row: dict,
    raw_key: str,
    discovery_run_id: str,
    seen_at: datetime,
) -> tuple[dict, dict]:
    event_ts = _utc_now()
    spot_version_id = str(uuid4())
    version_ts = event_ts
    event_row = {
        "event_ts": event_ts,
        "run_id": discovery_run_id,
        "spot_id": latest_row["spot_id"],
        "event_type": "removed",
        "source_type": "sitemap",
        "source_raw_key": raw_key,
        "old_checksum": latest_row.get("content_checksum"),
        "new_checksum": None,
        "spot_version_id": spot_version_id,
        "version_ts": version_ts,
    }
    core_row = {
        "spot_version_id": spot_version_id,
        "spot_id": latest_row["spot_id"],
        "version_ts": version_ts,
        "content_checksum": None,
        "event_type": "removed",
        "seen_at": seen_at,
        "sitemap_link": latest_row.get("sitemap_link"),
        "forecast_link": latest_row.get("forecast_link"),
        "source_run_id": discovery_run_id,
        "source_raw_key": raw_key,
        "source_type": "sitemap",
        "schema_version": SCHEMA_VERSION,
        "processed_at": event_ts,
    }
    return event_row, core_row


def _build_manifest(
    *,
    scrape_date: str,
    raw_payload: dict,
    raw_key: str,
    added_ids: list[str],
    removed_ids: list[str],
) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "manifest_type": "discovery_run",
        "discovery_run_id": raw_payload["run_id"],
        "sitemap_run_id": raw_payload["run_id"],
        "scrape_date": scrape_date,
        "source_type": "sitemap",
        "sitemap_raw_key": raw_key,
        "added_spot_ids": added_ids,
        "added_spot_count": len(added_ids),
        "removed_spot_ids": removed_ids,
        "removed_count": len(removed_ids),
        "created_at": _utc_now().isoformat(),
    }


def _queue_spot_scrapes(queue_url: str, manifest: dict, source_raw_key: str) -> None:
    for spot_id in manifest["added_spot_ids"]:
        sqs_client.send_message(
            QueueUrl=queue_url,
            MessageBody=json.dumps(
                {
                    "spot_id": spot_id,
                    "discovery_run_id": manifest["discovery_run_id"],
                    "sitemap_run_id": manifest["sitemap_run_id"],
                    "source_raw_key": source_raw_key,
                    "requested_at": _utc_now().isoformat(),
                }
            ),
        )


@inject_lambda_context(log_event=False)
def lambda_handler(event: dict, context: LambdaContext):
    bucket, key = _parse_s3_reference(event)
    raw_payload = s3_client.get_json(bucket, key)
    if raw_payload is None:
        raise FileNotFoundError(f"Missing raw sitemap payload: s3://{bucket}/{key}")

    discovery_run_id = raw_payload["run_id"]
    scrape_date = raw_payload["scraped_at"][:10]
    manifest_key = _discovery_manifest_key(scrape_date=scrape_date, discovery_run_id=discovery_run_id)
    if s3_client.object_exists(bucket, manifest_key):
        logger.info("Discovery run already processed", extra={"manifest_key": manifest_key})
        return {"statusCode": 200, "body": "duplicate sitemap event ignored"}

    latest_rows = s3_client.get_parquet_rows(bucket, CATALOG_CORE_KEY)
    latest_by_spot_id = {row["spot_id"]: row for row in latest_rows}
    sitemap_spots = raw_payload["spots"]

    added_ids = sorted(set(sitemap_spots) - set(latest_by_spot_id))
    removed_ids = sorted(set(latest_by_spot_id) - set(sitemap_spots))
    seen_at = datetime.fromisoformat(raw_payload["scraped_at"])

    event_rows = [_build_added_event(spot_id, key, discovery_run_id, _utc_now()) for spot_id in added_ids]
    tombstone_rows: list[dict] = []
    for spot_id in removed_ids:
        event_row, core_row = _build_removed_rows(
            latest_row=latest_by_spot_id[spot_id],
            raw_key=key,
            discovery_run_id=discovery_run_id,
            seen_at=seen_at,
        )
        event_rows.append(event_row)
        tombstone_rows.append(core_row)

    if event_rows:
        s3_client.put_parquet(bucket, _events_key(_utc_now()), event_rows)
    if tombstone_rows:
        s3_client.put_parquet(bucket, _core_key(_utc_now()), tombstone_rows)

    manifest = _build_manifest(
        scrape_date=scrape_date,
        raw_payload=raw_payload,
        raw_key=key,
        added_ids=added_ids,
        removed_ids=removed_ids,
    )
    s3_client.put_json(bucket, manifest_key, manifest)

    if added_ids:
        queue_url = os.environ["SPOT_SCRAPER_QUEUE_URL"]
        _queue_spot_scrapes(queue_url=queue_url, manifest=manifest, source_raw_key=key)
    else:
        s3_client.put_json(
            bucket,
            _processing_manifest_key(scrape_date, discovery_run_id, "catalog_build"),
            {
                "schema_version": SCHEMA_VERSION,
                "manifest_type": "processing_manifest",
                "domain": "discovery",
                "stage": "catalog_build",
                "discovery_run_id": discovery_run_id,
                "scrape_date": scrape_date,
                "source_manifest_key": manifest_key,
                "source_keys": [key],
                "ready_at": _utc_now().isoformat(),
            },
        )

    logger.info(
        "Discovery diff complete",
        extra={
            "bucket": bucket,
            "key": key,
            "added_count": len(added_ids),
            "removed_count": len(removed_ids),
        },
    )
    return {
        "statusCode": 200,
        "body": json.dumps(
            {
                "added_count": len(added_ids),
                "removed_count": len(removed_ids),
                "manifest_key": manifest_key,
            }
        ),
    }
