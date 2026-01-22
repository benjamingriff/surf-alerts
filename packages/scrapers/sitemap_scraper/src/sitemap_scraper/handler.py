import os
from datetime import datetime, timezone

from aws_lambda_powertools.utilities.typing import LambdaContext

from sitemap_scraper.io import S3Writer
from sitemap_scraper.logger import get_logger, inject_lambda_context
from sitemap_scraper.scraper import scrape_sitemap

logger = get_logger()

s3_writer = S3Writer()


@inject_lambda_context(log_event=False)
def lambda_handler(event: dict, context: LambdaContext):
    """Lambda handler triggered by EventBridge schedule.

    Scrapes Surfline sitemap and saves to S3.
    """
    logger.debug("Received event", extra={"event": event})

    bucket = os.environ.get("BUCKET_NAME", "surf-alerts-data")

    result = scrape_sitemap()

    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    key = f"spots/{date_str}/sitemap.json"

    s3_path = s3_writer.put_json(bucket=bucket, key=key, body=result)

    logger.info(
        "Sitemap data saved to S3",
        extra={"s3_path": s3_path, "spot_count": len(result["spots"])},
    )

    return {
        "statusCode": 200,
        "body": f"Sitemap scraped: {len(result['spots'])} spots saved to {s3_path}",
    }
