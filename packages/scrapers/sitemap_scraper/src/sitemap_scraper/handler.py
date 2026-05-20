import json
import os
import hashlib
from datetime import datetime, timezone

import boto3
from aws_lambda_powertools.utilities.typing import LambdaContext
from botocore.exceptions import ClientError

from sitemap_scraper.io import S3Writer
from sitemap_scraper.logger import get_logger, inject_lambda_context
from sitemap_scraper.scraper import scrape_sitemap
from sitemap_scraper.storage import build_sitemap_payload

logger = get_logger()
s3_writer = S3Writer()
s3_client = boto3.client("s3")
sqs_client = boto3.client("sqs")


def _exists(bucket: str, key: str) -> bool:
    try:
        s3_client.head_object(Bucket=bucket, Key=key)
        return True
    except ClientError as e:
        if e.response["Error"]["Code"] in {"404", "NoSuchKey", "NotFound"}:
            return False
        raise


def _key(scrape_date: str, run_id: str) -> str:
    return f"raw/sitemap/scrape_date={scrape_date}/discovery_run_id={run_id}.json.gz"


@inject_lambda_context(log_event=False)
def lambda_handler(event: dict, context: LambdaContext):
    bucket = os.environ.get("DATA_BUCKET", os.environ.get("BUCKET_NAME", "surf-alerts-data"))
    now = datetime.now(timezone.utc).replace(microsecond=0)
    scrape_date = event.get("scrape_date") or now.date().isoformat()
    run_id = hashlib.sha256(f"discovery:{scrape_date}".encode()).hexdigest()
    key = _key(scrape_date, run_id)

    if not _exists(bucket, key):
        result = scrape_sitemap()
        payload = build_sitemap_payload(result=result, run_id=run_id)
        payload["discovery_run_id"] = run_id
        payload["scrape_date"] = scrape_date
        s3_writer.put_json(bucket=bucket, key=key, body=payload)

    msg = {
        "schema_version": 1,
        "message_type": "sitemap_scrape_complete",
        "discovery_run_id": run_id,
        "scrape_date": scrape_date,
        "raw_bucket": bucket,
        "raw_key": key,
        "completed_at": now.isoformat().replace("+00:00", "Z"),
    }
    sqs_client.send_message(
        QueueUrl=os.environ["DISCOVERY_RUN_PLANNER_QUEUE_URL"], MessageBody=json.dumps(msg)
    )
    return {"statusCode": 200, "body": json.dumps(msg)}
