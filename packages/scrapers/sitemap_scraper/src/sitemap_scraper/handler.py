import os
from datetime import datetime
from uuid import uuid4

from aws_lambda_powertools.utilities.typing import LambdaContext

from sitemap_scraper.io import S3Writer
from sitemap_scraper.logger import get_logger, inject_lambda_context
from sitemap_scraper.scraper import scrape_sitemap
from sitemap_scraper.storage import build_sitemap_key, build_sitemap_payload

logger = get_logger()

s3_writer = S3Writer()


@inject_lambda_context(log_event=False)
def lambda_handler(event: dict, context: LambdaContext):
    """Lambda handler triggered by EventBridge schedule.

    Scrapes Surfline sitemap and saves to S3.
    """
    logger.debug("Received event", extra={"event": event})

    bucket = os.environ.get("DATA_BUCKET", os.environ.get("BUCKET_NAME", "surf-alerts-data"))

    result = scrape_sitemap()
    run_id = str(uuid4())
    payload = build_sitemap_payload(result=result, run_id=run_id)
    scraped_at = datetime.fromisoformat(payload["scraped_at"])
    key = build_sitemap_key(scraped_at=scraped_at, run_id=run_id)

    s3_path = s3_writer.put_json(bucket=bucket, key=key, body=payload)

    logger.info(
        "Sitemap data saved to S3",
        extra={"s3_path": s3_path, "spot_count": payload["spot_count"], "run_id": run_id},
    )

    return {
        "statusCode": 200,
        "body": f"Sitemap scraped: {payload['spot_count']} spots saved to {s3_path}",
    }
