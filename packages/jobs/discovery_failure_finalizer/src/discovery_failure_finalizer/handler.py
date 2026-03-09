import json
import os
from datetime import datetime, timezone
from uuid import uuid4

from aws_lambda_powertools.utilities.typing import LambdaContext

from discovery_failure_finalizer.logger import get_logger, inject_lambda_context
from discovery_failure_finalizer.s3 import S3Client

logger = get_logger()
s3_client = S3Client()
SCHEMA_VERSION = 1


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _resolve_bucket() -> str:
    return os.environ.get("DATA_BUCKET", os.environ.get("BUCKET_NAME", "surf-alerts-data"))


def _extract_scrape_date(message_body: dict, failed_at: datetime) -> str:
    source_raw_key = message_body.get("source_raw_key", "")
    for part in source_raw_key.split("/"):
        if part.startswith("scrape_date="):
            return part.removeprefix("scrape_date=")

    requested_at = message_body.get("requested_at")
    if requested_at:
        return requested_at[:10]
    return failed_at.strftime("%Y-%m-%d")


def _failure_key(scrape_date: str, discovery_run_id: str, spot_id: str) -> str:
    return (
        "control/completions/discovery_spot_scrapes_failed/"
        f"date={scrape_date}/discovery_run_id={discovery_run_id}/spot_id={spot_id}.json.gz"
    )


def _build_failure_payload(record: dict, message_body: dict, failed_at: datetime) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "source_type": "spot_scrape_failure",
        "terminal_status": "failed",
        "discovery_run_id": message_body["discovery_run_id"],
        "spot_id": message_body["spot_id"],
        "completed_at": failed_at.isoformat(),
        "failure_reason": "scrape_failed_after_max_retries",
        "failure_source": "spot_scraper_dlq",
        "failure_id": str(uuid4()),
        "original_message_id": record.get("messageId"),
        "approximate_receive_count": record.get("attributes", {}).get("ApproximateReceiveCount"),
        "source_raw_key": message_body.get("source_raw_key"),
        "requested_at": message_body.get("requested_at"),
        "sitemap_run_id": message_body.get("sitemap_run_id"),
    }


@inject_lambda_context(log_event=False)
def lambda_handler(event: dict, context: LambdaContext):
    logger.debug("Received event", extra={"event": event})

    bucket = _resolve_bucket()
    processed_count = 0
    skipped_count = 0

    for record in event["Records"]:
        message_body = json.loads(record["body"])
        discovery_run_id = message_body.get("discovery_run_id")
        spot_id = message_body.get("spot_id")
        if not discovery_run_id or not spot_id:
            skipped_count += 1
            logger.warning("Skipping DLQ record missing discovery context", extra={"record": record})
            continue

        failed_at = _utc_now()
        scrape_date = _extract_scrape_date(message_body, failed_at)
        s3_client.put_json(
            bucket=bucket,
            key=_failure_key(scrape_date, discovery_run_id, spot_id),
            body=_build_failure_payload(record, message_body, failed_at),
        )
        processed_count += 1

    return {
        "statusCode": 200,
        "body": json.dumps(
            {
                "failed_markers_written": processed_count,
                "skipped_records": skipped_count,
            }
        ),
    }
