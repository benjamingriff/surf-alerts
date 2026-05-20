import json
import os
from datetime import datetime, timezone
from typing import Any

import boto3
from aws_lambda_powertools.utilities.typing import LambdaContext
from botocore.exceptions import ClientError

from spot_scraper.io import S3Writer
from spot_scraper.logger import get_logger, inject_lambda_context
from spot_scraper.storage import build_raw_spot_payload, build_spot_report_key

logger = get_logger()
SCHEMA_VERSION = 1


def _s3_client():
    return boto3.client("s3")


def _sqs_client():
    return boto3.client("sqs")


def _s3_writer():
    return S3Writer()


def _fetch_spot_report(spot_id: str) -> dict:
    from spot_scraper.scraper.core import fetch_spot_report

    return fetch_spot_report(spot_id)


def _exists(bucket: str, key: str) -> bool:
    try:
        _s3_client().head_object(Bucket=bucket, Key=key)
        return True
    except ClientError as e:
        if e.response["Error"]["Code"] in {"404", "NoSuchKey", "NotFound"}:
            return False
        raise


def _send_completion(payload: dict) -> None:
    _sqs_client().send_message(
        QueueUrl=os.environ["DISCOVERY_COMPLETION_QUEUE_URL"], MessageBody=json.dumps(payload)
    )


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _success_completion(
    *,
    discovery_run_id: str,
    scrape_date: str,
    spot_id: str,
    bucket: str,
    key: str,
    completed_at: str,
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "message_type": "spot_scrape_complete",
        "terminal_status": "success",
        "discovery_run_id": discovery_run_id,
        "scrape_date": scrape_date,
        "spot_id": spot_id,
        "raw_bucket": bucket,
        "raw_key": key,
        "completed_at": completed_at,
    }


def _failure_completion(
    *, discovery_run_id: str, scrape_date: str, spot_id: str, failure_reason: str, failed_at: str
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "message_type": "spot_scrape_complete",
        "terminal_status": "failed",
        "discovery_run_id": discovery_run_id,
        "scrape_date": scrape_date,
        "spot_id": spot_id,
        "raw_bucket": None,
        "raw_key": None,
        "failure_reason": failure_reason,
        "failure_source": "spot_scraper",
        "failed_at": failed_at,
    }


def process_spot_scrape_request(
    message: dict[str, Any], *, bucket: str | None = None
) -> dict[str, Any]:
    bucket = bucket or os.environ.get(
        "DATA_BUCKET", os.environ.get("BUCKET_NAME", "surf-alerts-data")
    )
    spot_id = message["spot_id"]
    discovery_run_id = message["discovery_run_id"]
    scrape_date = message["scrape_date"]
    key = build_spot_report_key(
        scrape_date=scrape_date,
        discovery_run_id=discovery_run_id,
        spot_id=spot_id,
    )
    now = _utc_now_iso()

    try:
        if not _exists(bucket, key):
            raw_payload = _fetch_spot_report(spot_id)
            body = build_raw_spot_payload(
                spot_id=spot_id,
                raw_payload=raw_payload,
                run_id=discovery_run_id,
                scraped_at=now,
                discovery_run_id=discovery_run_id,
                sitemap_run_id=None,
                source_raw_key=message.get("sitemap_raw_key"),
                requested_at=message.get("requested_at"),
            )
            _s3_writer().put_json(bucket=bucket, key=key, body=body)

        completion = _success_completion(
            discovery_run_id=discovery_run_id,
            scrape_date=scrape_date,
            spot_id=spot_id,
            bucket=bucket,
            key=key,
            completed_at=now,
        )
        _send_completion(completion)
        return completion
    except Exception as e:
        logger.warning("Spot scrape failed", extra={"spot_id": spot_id, "error": str(e)})
        completion = _failure_completion(
            discovery_run_id=discovery_run_id,
            scrape_date=scrape_date,
            spot_id=spot_id,
            failure_reason=str(e),
            failed_at=now,
        )
        _send_completion(completion)
        return completion


@inject_lambda_context(log_event=False)
def lambda_handler(event: dict, context: LambdaContext):
    bucket = os.environ.get("DATA_BUCKET", os.environ.get("BUCKET_NAME", "surf-alerts-data"))
    results = [
        process_spot_scrape_request(json.loads(record["body"]), bucket=bucket)
        for record in event["Records"]
    ]
    return {"statusCode": 200, "body": json.dumps({"processed": len(results)})}
