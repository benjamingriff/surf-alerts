import json

from aws_lambda_powertools.utilities.typing import LambdaContext

from spot_scraper.io.s3 import S3Writer
from spot_scraper.logger import get_logger, inject_lambda_context
from spot_scraper.scraper import scrape_spot

logger = get_logger()

s3_writer = S3Writer()


@inject_lambda_context(log_event=False)
def lambda_handler(event: dict, context: LambdaContext):
    logger.debug("Received event", extra={"event": event})

    num_records = len(event["Records"])

    for record in event["Records"]:
        message_body = json.loads(record["body"])
        spot_id = message_body["spot_id"]
        results = scrape_spot(spot_id)
        s3_writer.put_json(
            bucket=message_body["bucket"],
            key=message_body["prefix"],
            body=results,
        )

    return {
        "statusCode": 200,
        "body": f"{num_records} spots data scraped and saved to S3",
    }
