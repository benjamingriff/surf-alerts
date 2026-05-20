import json
import os
from datetime import datetime, timezone
from typing import Any

import boto3
from aws_lambda_powertools.utilities.typing import LambdaContext

from discovery_completion.logger import get_logger, inject_lambda_context
from discovery_control import (
    ControlStore,
    RUN_STATUS_SPOT_PROCESSING_QUEUED,
    RUN_STATUS_SPOT_SCRAPES_COMPLETE,
    RUN_STATUS_WAITING_FOR_SPOT_SCRAPES,
)

logger = get_logger()
SCHEMA_VERSION = 1


def _store() -> ControlStore:
    return ControlStore()


def _sqs_client():
    return boto3.client("sqs")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _completion_timestamp(payload: dict[str, Any]) -> str:
    return payload.get("completed_at") or payload.get("failed_at") or _utc_now_iso()


def build_batch_processor_message(*, discovery_run_id: str, requested_at: str) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "message_type": "discovery_spot_batch_process_requested",
        "discovery_run_id": discovery_run_id,
        "requested_at": requested_at,
    }


def _batch_processor_queue_url() -> str:
    return os.environ["DISCOVERY_SPOT_BATCH_PROCESSOR_QUEUE_URL"]


def _send_batch_processor_request(*, discovery_run_id: str) -> None:
    _sqs_client().send_message(
        QueueUrl=_batch_processor_queue_url(),
        MessageBody=json.dumps(
            build_batch_processor_message(
                discovery_run_id=discovery_run_id,
                requested_at=_utc_now_iso(),
            )
        ),
    )


def process_completion_message(payload: dict[str, Any], *, store: ControlStore | None = None) -> str:
    store = store or _store()
    discovery_run_id = payload["discovery_run_id"]
    newly_terminal = store.mark_spot_terminal(
        discovery_run_id=discovery_run_id,
        spot_id=payload["spot_id"],
        terminal_status=payload["terminal_status"],
        completed_at=_completion_timestamp(payload),
        raw_key=payload.get("raw_key"),
        raw_bucket=payload.get("raw_bucket"),
        failure_reason=payload.get("failure_reason"),
        failure_source=payload.get("failure_source"),
    )
    if not newly_terminal:
        return "duplicate"

    run = store.get_run(discovery_run_id)
    if run is None:
        raise FileNotFoundError(f"Missing discovery run state: {discovery_run_id}")

    if run.get("terminal_scrape_count") != run.get("expected_spot_count"):
        return "recorded"

    transitioned_to_complete = store.transition_run_status(
        discovery_run_id=discovery_run_id,
        from_status=RUN_STATUS_WAITING_FOR_SPOT_SCRAPES,
        to_status=RUN_STATUS_SPOT_SCRAPES_COMPLETE,
    )
    if not transitioned_to_complete:
        return "recorded"

    queued = store.transition_run_status(
        discovery_run_id=discovery_run_id,
        from_status=RUN_STATUS_SPOT_SCRAPES_COMPLETE,
        to_status=RUN_STATUS_SPOT_PROCESSING_QUEUED,
    )
    if queued:
        _send_batch_processor_request(discovery_run_id=discovery_run_id)
        return "queued_batch_processor"

    return "recorded"


@inject_lambda_context(log_event=False)
def lambda_handler(event: dict, context: LambdaContext):
    processed = 0
    deduplicated = 0
    queued = 0
    store = _store()

    for record in event["Records"]:
        result = process_completion_message(json.loads(record["body"]), store=store)
        if result == "duplicate":
            deduplicated += 1
        else:
            processed += 1
        if result == "queued_batch_processor":
            queued += 1

    logger.info(
        "Discovery completion batch reduced",
        extra={"processed": processed, "deduplicated": deduplicated, "queued": queued},
    )
    return {
        "statusCode": 200,
        "body": json.dumps({"processed": processed, "deduplicated": deduplicated, "queued": queued}),
    }
