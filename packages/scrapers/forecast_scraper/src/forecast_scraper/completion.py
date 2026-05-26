import json

import boto3
from botocore.exceptions import ClientError

from forecast_scraper.logger import get_logger

logger = get_logger()


class CompletionSender:
    def __init__(self, queue_url: str, sqs_client=None):
        self.queue_url = queue_url
        self.sqs = sqs_client or boto3.client("sqs")

    def send_success(
        self, *, request: dict, raw_bucket: str, raw_key: str, scraped_at: str
    ) -> None:
        self._send(
            {
                "schema_version": request.get("schema_version", 1),
                "message_type": "forecast_spot_scrape_completed",
                "scrape_status": "success",
                "forecast_run_id": request["forecast_run_id"],
                "scheduled_utc_time": request["scheduled_utc_time"],
                "scrape_date": request["scrape_date"],
                "spot_id": request["spot_id"],
                "spot_version_id": request.get("spot_version_id"),
                "utc_offset": request.get("utc_offset"),
                "timezone": request.get("timezone"),
                "scraped_at": scraped_at,
                "raw_bucket": raw_bucket,
                "raw_key": raw_key,
            }
        )

    def send_failure(self, *, request: dict, failure_source: str, failure_reason: str) -> None:
        self._send(
            {
                "schema_version": request.get("schema_version", 1),
                "message_type": "forecast_spot_scrape_completed",
                "scrape_status": "failed",
                "forecast_run_id": request["forecast_run_id"],
                "scheduled_utc_time": request["scheduled_utc_time"],
                "scrape_date": request["scrape_date"],
                "spot_id": request["spot_id"],
                "spot_version_id": request.get("spot_version_id"),
                "utc_offset": request.get("utc_offset"),
                "timezone": request.get("timezone"),
                "raw_bucket": None,
                "raw_key": None,
                "failure_source": failure_source,
                "failure_reason": failure_reason[:1000],
            }
        )

    def _send(self, message: dict) -> None:
        try:
            self.sqs.send_message(QueueUrl=self.queue_url, MessageBody=json.dumps(message))
        except ClientError:
            logger.exception("forecast_completion_send_failed")
            raise
