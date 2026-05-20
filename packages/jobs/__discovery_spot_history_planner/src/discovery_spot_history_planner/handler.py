import json
import os
from math import ceil

import boto3
from aws_lambda_powertools.utilities.typing import LambdaContext

from discovery_control import (
    ControlStore,
    RUN_STATUS_CATALOG_BUILD_READY,
    RUN_STATUS_SPOT_HISTORY_IN_PROGRESS,
    RUN_STATUS_SPOT_HISTORY_READY,
)
from discovery_spot_history_planner.logger import get_logger, inject_lambda_context

logger = get_logger()
store = ControlStore()
sqs_client = boto3.client("sqs")


def _planner_queue_url() -> str:
    return os.environ["DISCOVERY_SPOT_HISTORY_CHUNK_QUEUE_URL"]


def _catalog_build_queue_url() -> str:
    return os.environ["DISCOVERY_CATALOG_BUILD_QUEUE_URL"]


def _chunk_size() -> int:
    return int(os.environ.get("DISCOVERY_SPOT_HISTORY_CHUNK_SIZE", "250"))


def _chunks(spots: list[dict]) -> list[dict]:
    chunked: list[dict] = []
    if not spots:
        return chunked
    chunk_size = _chunk_size()
    for index in range(ceil(len(spots) / chunk_size)):
        batch = spots[index * chunk_size : (index + 1) * chunk_size]
        chunked.append(
            {
                "chunk_id": f"chunk-{index + 1:04d}",
                "spot_ids": [item["spot_id"] for item in batch],
                "raw_keys": [item["raw_key"] for item in batch],
            }
        )
    return chunked


@inject_lambda_context(log_event=False)
def lambda_handler(event: dict, context: LambdaContext):
    processed = 0
    for record in event["Records"]:
        payload = json.loads(record["body"])
        discovery_run_id = payload["discovery_run_id"]
        run = store.get_run(discovery_run_id)
        if run is None:
            raise FileNotFoundError(f"Missing discovery run state: {discovery_run_id}")

        if run["status"] == RUN_STATUS_CATALOG_BUILD_READY:
            continue
        if run["status"] == RUN_STATUS_SPOT_HISTORY_IN_PROGRESS:
            continue
        if run["status"] != RUN_STATUS_SPOT_HISTORY_READY:
            raise ValueError(f"Unexpected run status for planning: {run['status']}")

        successful_spots = store.list_spots(discovery_run_id, terminal_status="success")
        if not successful_spots:
            if store.transition_run_status(
                discovery_run_id=discovery_run_id,
                from_status=RUN_STATUS_SPOT_HISTORY_READY,
                to_status=RUN_STATUS_CATALOG_BUILD_READY,
            ):
                sqs_client.send_message(
                    QueueUrl=_catalog_build_queue_url(),
                    MessageBody=json.dumps({"discovery_run_id": discovery_run_id}),
                )
            processed += 1
            continue

        chunks = _chunks(successful_spots)
        store.create_chunks(discovery_run_id=discovery_run_id, chunks=chunks)
        queue_url = _planner_queue_url()
        for chunk in chunks:
            sqs_client.send_message(
                QueueUrl=queue_url,
                MessageBody=json.dumps(
                    {
                        "discovery_run_id": discovery_run_id,
                        "chunk_id": chunk["chunk_id"],
                    }
                ),
            )

        logger.info(
            "Spot history chunks planned",
            extra={
                "discovery_run_id": discovery_run_id,
                "chunk_count": len(chunks),
                "successful_spot_count": len(successful_spots),
            },
        )
        processed += 1

    return {"statusCode": 200, "body": f"planned {processed} discovery run(s)"}
