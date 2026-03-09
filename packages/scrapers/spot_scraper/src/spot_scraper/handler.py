import json
import os
from datetime import datetime, timezone
from uuid import uuid4

from aws_lambda_powertools.utilities.typing import LambdaContext

from spot_scraper.io import S3Writer
from spot_scraper.logger import get_logger, inject_lambda_context
from spot_scraper.storage import build_raw_spot_payload, build_spot_report_key

logger = get_logger()

s3_writer = S3Writer()

SCHEMA_VERSION = 1


def _fetch_spot_report(spot_id: str) -> dict:
    from spot_scraper.scraper.core import fetch_spot_report

    return fetch_spot_report(spot_id)


def _resolve_output(message_body: dict, spot_id: str, scraped_at: datetime, run_id: str) -> tuple[str, str]:
    legacy_bucket = message_body.get("bucket")
    legacy_prefix = message_body.get("prefix")
    if legacy_bucket and legacy_prefix:
        return legacy_bucket, legacy_prefix

    bucket = os.environ.get("DATA_BUCKET", os.environ.get("BUCKET_NAME", "surf-alerts-data"))
    return bucket, build_spot_report_key(spot_id=spot_id, scraped_at=scraped_at, run_id=run_id)


def _completion_key(scrape_date: str, discovery_run_id: str, spot_id: str) -> str:
    return (
        "control/completions/discovery_spot_scrapes/"
        f"date={scrape_date}/discovery_run_id={discovery_run_id}/spot_id={spot_id}.json.gz"
    )


@inject_lambda_context(log_event=False)
def lambda_handler(event: dict, context: LambdaContext):
    logger.debug("Received event", extra={"event": event})

    num_records = len(event["Records"])

    for record in event["Records"]:
        message_body = json.loads(record["body"])
        spot_id = message_body["spot_id"]
        run_id = str(uuid4())
        raw_payload = _fetch_spot_report(spot_id)
        scraped_at_dt = datetime.now(timezone.utc).replace(microsecond=0)
        scraped_at = scraped_at_dt.isoformat().replace("+00:00", "Z")
        result = build_raw_spot_payload(
            spot_id=spot_id,
            raw_payload=raw_payload,
            run_id=run_id,
            scraped_at=scraped_at,
            discovery_run_id=message_body.get("discovery_run_id"),
            sitemap_run_id=message_body.get("sitemap_run_id"),
            source_raw_key=message_body.get("source_raw_key"),
            requested_at=message_body.get("requested_at"),
        )
        bucket, key = _resolve_output(
            message_body=message_body,
            spot_id=spot_id,
            scraped_at=scraped_at_dt,
            run_id=run_id,
        )
        s3_writer.put_json(bucket=bucket, key=key, body=result)

        discovery_run_id = message_body.get("discovery_run_id")
        if discovery_run_id:
            s3_writer.put_json(
                bucket=bucket,
                key=_completion_key(
                    scrape_date=scraped_at_dt.strftime("%Y-%m-%d"),
                    discovery_run_id=discovery_run_id,
                    spot_id=spot_id,
                ),
                body={
                    "schema_version": SCHEMA_VERSION,
                    "source_type": "spot_scrape_completion",
                    "terminal_status": "success",
                    "discovery_run_id": discovery_run_id,
                    "spot_id": spot_id,
                    "raw_run_id": run_id,
                    "raw_key": key,
                    "completed_at": datetime.now(timezone.utc).isoformat(),
                },
            )

    return {
        "statusCode": 200,
        "body": f"{num_records} spot(s) scraped and saved to S3",
    }
