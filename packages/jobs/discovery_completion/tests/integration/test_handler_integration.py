import json
import os

import boto3

from discovery_completion.handler import lambda_handler
from discovery_control import ControlStore


def _control_store():
    return ControlStore(
        table_name=os.environ["DISCOVERY_CONTROL_TABLE_NAME"],
        dynamodb_resource=boto3.resource("dynamodb", region_name="eu-west-2"),
    )


def _messages(queue_url: str) -> list[dict]:
    sqs = boto3.client("sqs", region_name="eu-west-2")
    messages = sqs.receive_message(QueueUrl=queue_url, MaxNumberOfMessages=10).get("Messages", [])
    return [json.loads(message["Body"]) for message in messages]


def test_records_success_and_failure_then_queues_batch_processor_once(monkeypatch, lambda_context):
    sqs = boto3.client("sqs", region_name="eu-west-2")
    queue_url = sqs.create_queue(QueueName="completion-batch")["QueueUrl"]
    monkeypatch.setenv("DISCOVERY_SPOT_BATCH_PROCESSOR_QUEUE_URL", queue_url)
    monkeypatch.setattr("discovery_completion.handler._utc_now_iso", lambda: "2026-05-01T06:10:00Z")
    store = _control_store()
    store.seed_run(
        discovery_run_id="run-1",
        scrape_date="2026-05-01",
        sitemap_raw_key="raw/sitemap/x.json.gz",
        expected_spot_count=2,
    )
    store.seed_spots(discovery_run_id="run-1", spot_ids=["a", "b"])

    response = lambda_handler(
        {
            "Records": [
                {
                    "body": json.dumps(
                        {
                            "discovery_run_id": "run-1",
                            "spot_id": "a",
                            "terminal_status": "success",
                            "raw_bucket": "bucket",
                            "raw_key": "raw/a.json.gz",
                            "completed_at": "2026-05-01T06:02:00Z",
                        }
                    )
                },
                {
                    "body": json.dumps(
                        {
                            "discovery_run_id": "run-1",
                            "spot_id": "b",
                            "terminal_status": "failed",
                            "failure_reason": "HTTP 403",
                            "failure_source": "spot_scraper",
                            "failed_at": "2026-05-01T06:03:00Z",
                        }
                    )
                },
            ]
        },
        lambda_context,
    )

    assert response["statusCode"] == 200
    assert json.loads(response["body"]) == {"processed": 2, "deduplicated": 0, "queued": 1}
    run = store.get_run("run-1")
    assert run["status"] == "spot_processing_queued"
    assert run["terminal_scrape_count"] == 2
    assert run["success_scrape_count"] == 1
    assert run["failed_scrape_count"] == 1
    spots = {spot["spot_id"]: spot for spot in store.list_spots("run-1")}
    assert spots["a"]["terminal_status"] == "success"
    assert spots["a"]["raw_key"] == "raw/a.json.gz"
    assert spots["b"]["terminal_status"] == "failed"
    assert spots["b"]["failure_reason"] == "HTTP 403"
    assert _messages(queue_url) == [
        {
            "schema_version": 1,
            "message_type": "discovery_spot_batch_process_requested",
            "discovery_run_id": "run-1",
            "requested_at": "2026-05-01T06:10:00Z",
        }
    ]


def test_duplicate_completion_is_deduplicated_and_does_not_increment_or_queue(
    monkeypatch, lambda_context
):
    sqs = boto3.client("sqs", region_name="eu-west-2")
    queue_url = sqs.create_queue(QueueName="completion-dedupe")["QueueUrl"]
    monkeypatch.setenv("DISCOVERY_SPOT_BATCH_PROCESSOR_QUEUE_URL", queue_url)
    store = _control_store()
    store.seed_run(
        discovery_run_id="run-dup",
        scrape_date="2026-05-01",
        sitemap_raw_key="raw/sitemap/x.json.gz",
        expected_spot_count=1,
    )
    store.seed_spots(discovery_run_id="run-dup", spot_ids=["a"])
    event = {
        "Records": [
            {
                "body": json.dumps(
                    {
                        "discovery_run_id": "run-dup",
                        "spot_id": "a",
                        "terminal_status": "success",
                        "raw_bucket": "bucket",
                        "raw_key": "raw/a.json.gz",
                        "completed_at": "2026-05-01T06:02:00Z",
                    }
                )
            },
            {
                "body": json.dumps(
                    {
                        "discovery_run_id": "run-dup",
                        "spot_id": "a",
                        "terminal_status": "success",
                        "raw_bucket": "bucket",
                        "raw_key": "raw/a.json.gz",
                        "completed_at": "2026-05-01T06:02:00Z",
                    }
                )
            },
        ]
    }

    response = lambda_handler(event, lambda_context)

    assert json.loads(response["body"])["deduplicated"] == 1
    run = store.get_run("run-dup")
    assert run["terminal_scrape_count"] == 1
    assert run["success_scrape_count"] == 1
    assert len(_messages(queue_url)) == 1


def test_not_all_terminal_does_not_queue_batch_processor(monkeypatch, lambda_context):
    sqs = boto3.client("sqs", region_name="eu-west-2")
    queue_url = sqs.create_queue(QueueName="completion-not-ready")["QueueUrl"]
    monkeypatch.setenv("DISCOVERY_SPOT_BATCH_PROCESSOR_QUEUE_URL", queue_url)
    store = _control_store()
    store.seed_run(
        discovery_run_id="run-wait",
        scrape_date="2026-05-01",
        sitemap_raw_key="raw/sitemap/x.json.gz",
        expected_spot_count=2,
    )
    store.seed_spots(discovery_run_id="run-wait", spot_ids=["a", "b"])

    lambda_handler(
        {
            "Records": [
                {
                    "body": json.dumps(
                        {
                            "discovery_run_id": "run-wait",
                            "spot_id": "a",
                            "terminal_status": "success",
                            "raw_bucket": "bucket",
                            "raw_key": "raw/a.json.gz",
                            "completed_at": "2026-05-01T06:02:00Z",
                        }
                    )
                }
            ]
        },
        lambda_context,
    )

    run = store.get_run("run-wait")
    assert run["status"] == "waiting_for_spot_scrapes"
    assert run["terminal_scrape_count"] == 1
    assert _messages(queue_url) == []
