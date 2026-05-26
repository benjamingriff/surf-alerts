import json
import os

from aws_lambda_powertools.utilities.typing import LambdaContext

from forecast_scraper.completion import CompletionSender
from forecast_scraper.io.s3 import S3Writer
from forecast_scraper.logger import get_logger, inject_lambda_context
from forecast_scraper.raw import build_raw_envelope, build_raw_key, utc_now_iso
from forecast_scraper.scraper import scrape_forecast

logger = get_logger()

s3_writer = S3Writer()


def _completion_sender() -> CompletionSender:
    return CompletionSender(queue_url=os.environ["FORECAST_COMPLETION_QUEUE_URL"])


def _raw_bucket(message_body: dict) -> str:
    return message_body.get("raw_bucket") or message_body.get("bucket") or os.environ["DATA_BUCKET"]


def _failure_source(error: Exception) -> str:
    module = error.__class__.__module__
    if "curl_cffi" in module or "requests" in module:
        return "fetch"
    if isinstance(error, (json.JSONDecodeError, ValueError, TypeError, KeyError)):
        return "parse"
    return "scrape"


def process_record(message_body: dict, *, completion_sender: CompletionSender | None = None) -> str:
    completion_sender = completion_sender or _completion_sender()
    spot_id = message_body["spot_id"]

    try:
        payload = scrape_forecast(spot_id)
    except Exception as error:
        failure_source = _failure_source(error)
        logger.warning(
            "forecast_scrape_failed",
            extra={
                "forecast_run_id": message_body.get("forecast_run_id"),
                "spot_id": spot_id,
                "failure_source": failure_source,
                "failure_reason": str(error),
            },
        )
        completion_sender.send_failure(
            request=message_body,
            failure_source=failure_source,
            failure_reason=str(error),
        )
        return "failed"

    scraped_at = utc_now_iso()
    raw_key = build_raw_key(
        scrape_date=message_body["scrape_date"],
        utc_offset=message_body["utc_offset"],
        forecast_run_id=message_body["forecast_run_id"],
        spot_id=spot_id,
    )
    raw_bucket = _raw_bucket(message_body)
    envelope = build_raw_envelope(request=message_body, payload=payload, scraped_at=scraped_at)
    s3_writer.put_json(bucket=raw_bucket, key=raw_key, body=envelope)
    completion_sender.send_success(
        request=message_body, raw_bucket=raw_bucket, raw_key=raw_key, scraped_at=scraped_at
    )
    return "success"


@inject_lambda_context(log_event=False)
def lambda_handler(event: dict, context: LambdaContext):
    logger.debug("Received event", extra={"event": event})

    results = []
    for record in event["Records"]:
        results.append(process_record(json.loads(record["body"])))

    return {
        "statusCode": 200,
        "body": json.dumps({"processed": len(results), "results": results}),
    }
