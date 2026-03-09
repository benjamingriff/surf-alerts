import json
import os
from datetime import datetime
from uuid import uuid4

from aws_lambda_powertools.utilities.typing import LambdaContext

from spot_scraper.io import S3Writer
from spot_scraper.logger import get_logger, inject_lambda_context
from spot_scraper.scraper import fetch_spot_report
from spot_scraper.storage import build_raw_spot_payload, build_spot_report_key

logger = get_logger()

s3_writer = S3Writer()

def _resolve_output(message_body: dict, spot_id: str, scraped_at: datetime, run_id: str) -> tuple[str, str]:
    legacy_bucket = message_body.get("bucket")
    legacy_prefix = message_body.get("prefix")
    if legacy_bucket and legacy_prefix:
        return legacy_bucket, legacy_prefix

    bucket = os.environ.get("DATA_BUCKET", os.environ.get("BUCKET_NAME", "surf-alerts-data"))
    return bucket, build_spot_report_key(spot_id=spot_id, scraped_at=scraped_at, run_id=run_id)


@inject_lambda_context(log_event=False)
def lambda_handler(event: dict, context: LambdaContext):
    logger.debug("Received event", extra={"event": event})

    num_records = len(event["Records"])

    for record in event["Records"]:
        message_body = json.loads(record["body"])
        spot_id = message_body["spot_id"]
        run_id = str(uuid4())
        raw_payload = fetch_spot_report(spot_id)
        scraped_at = datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
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
            scraped_at=datetime.fromisoformat(scraped_at.replace("Z", "+00:00")),
            run_id=run_id,
        )
        s3_writer.put_json(
            bucket=bucket,
            key=key,
            body=result,
        )

    return {
        "statusCode": 200,
        "body": f"{num_records} spot(s) scraped and saved to S3",
    }
