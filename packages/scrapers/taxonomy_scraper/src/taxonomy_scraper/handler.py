import os
from datetime import datetime, timezone

from aws_lambda_powertools.utilities.typing import LambdaContext

from taxonomy_scraper.io import S3Writer
from taxonomy_scraper.logger import get_logger, inject_lambda_context
from taxonomy_scraper.scraper import scrape_taxonomy

logger = get_logger()

s3_writer = S3Writer()


@inject_lambda_context(log_event=False)
def lambda_handler(event: dict, context: LambdaContext):
    """Lambda handler triggered by EventBridge schedule.

    Recursively scrapes Surfline taxonomy API and saves to S3.
    """
    logger.debug("Received event", extra={"event": event})

    bucket = os.environ.get("BUCKET_NAME", "surf-alerts-data")

    result = scrape_taxonomy()

    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    key = f"taxonomy/{date_str}/taxonomy.json"

    s3_path = s3_writer.put_json(bucket=bucket, key=key, body=result)

    logger.info(
        "Taxonomy data saved to S3",
        extra={"s3_path": s3_path},
    )

    return {
        "statusCode": 200,
        "body": f"Taxonomy scraped and saved to {s3_path}",
    }
