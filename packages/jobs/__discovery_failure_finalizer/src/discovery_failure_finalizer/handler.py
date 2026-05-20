import json
import os
from datetime import datetime, timezone

import boto3
from aws_lambda_powertools.utilities.typing import LambdaContext

from discovery_failure_finalizer.logger import get_logger, inject_lambda_context

logger = get_logger()
sqs_client = boto3.client("sqs")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _completion_queue_url() -> str:
    return os.environ["DISCOVERY_COMPLETION_QUEUE_URL"]


@inject_lambda_context(log_event=False)
def lambda_handler(event: dict, context: LambdaContext):
    logger.debug("Received event", extra={"event": event})

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

        sqs_client.send_message(
            QueueUrl=_completion_queue_url(),
            MessageBody=json.dumps(
                {
                    "discovery_run_id": discovery_run_id,
                    "spot_id": spot_id,
                    "terminal_status": "failed",
                    "completed_at": _utc_now().isoformat(),
                    "failure_reason": "scrape_failed_after_max_retries",
                    "failure_source": "spot_scraper_dlq",
                }
            ),
        )
        processed_count += 1

    return {
        "statusCode": 200,
        "body": json.dumps(
            {
                "failed_messages_enqueued": processed_count,
                "skipped_records": skipped_count,
            }
        ),
    }
