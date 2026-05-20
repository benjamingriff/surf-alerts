import json
import os

import boto3

from discovery_control import ControlStore
from discovery_spot_history_planner.handler import lambda_handler


def _control_store():
    dynamodb = boto3.resource("dynamodb", region_name="eu-west-2")
    return ControlStore(
        table_name=os.environ["DISCOVERY_CONTROL_TABLE_NAME"],
        dynamodb_resource=dynamodb,
    )


def test_planner_creates_chunks_and_enqueues_chunk_work(monkeypatch, lambda_context):
    sqs_client = boto3.client("sqs", region_name="eu-west-2")
    chunk_queue_url = sqs_client.create_queue(QueueName="chunk-queue")["QueueUrl"]
    catalog_queue_url = sqs_client.create_queue(QueueName="catalog-queue")["QueueUrl"]
    monkeypatch.setenv("DISCOVERY_SPOT_HISTORY_CHUNK_QUEUE_URL", chunk_queue_url)
    monkeypatch.setenv("DISCOVERY_CATALOG_BUILD_QUEUE_URL", catalog_queue_url)
    monkeypatch.setenv("DISCOVERY_SPOT_HISTORY_CHUNK_SIZE", "2")

    store = _control_store()
    store.seed_run(
        discovery_run_id="run-1",
        scrape_date="2026-03-09",
        sitemap_raw_key="raw/sitemap/1.json.gz",
        expected_spot_count=3,
        removed_spot_ids=[],
    )
    store.seed_spots(discovery_run_id="run-1", spot_ids=["a", "b", "c"])
    store.mark_spot_terminal(
        discovery_run_id="run-1",
        spot_id="a",
        terminal_status="success",
        raw_key="raw/a.json.gz",
        completed_at="2026-03-09T06:01:00Z",
    )
    store.mark_spot_terminal(
        discovery_run_id="run-1",
        spot_id="b",
        terminal_status="success",
        raw_key="raw/b.json.gz",
        completed_at="2026-03-09T06:02:00Z",
    )
    store.mark_spot_terminal(
        discovery_run_id="run-1",
        spot_id="c",
        terminal_status="success",
        raw_key="raw/c.json.gz",
        completed_at="2026-03-09T06:03:00Z",
    )
    assert store.transition_run_status(
        discovery_run_id="run-1",
        from_status="waiting_for_spot_scrapes",
        to_status="spot_history_ready",
    )

    response = lambda_handler(
        {"Records": [{"body": json.dumps({"discovery_run_id": "run-1"})}]},
        lambda_context,
    )

    assert response["statusCode"] == 200
    run = store.get_run("run-1")
    assert run["status"] == "spot_history_in_progress"
    assert run["chunk_count"] == 2
    messages = sqs_client.receive_message(QueueUrl=chunk_queue_url, MaxNumberOfMessages=10)["Messages"]
    chunk_ids = sorted(json.loads(message["Body"])["chunk_id"] for message in messages)
    assert chunk_ids == ["chunk-0001", "chunk-0002"]
