import gzip
import json
import os

import boto3

from discovery_run_planner.handler import lambda_handler


def _queue_messages(queue_url: str) -> list[dict]:
    sqs = boto3.client("sqs", region_name="eu-west-2")
    messages = sqs.receive_message(QueueUrl=queue_url, MaxNumberOfMessages=10).get("Messages", [])
    return [json.loads(m["Body"]) for m in messages]


def _run_item(run_id: str) -> dict:
    dynamodb = boto3.resource("dynamodb", region_name="eu-west-2")
    table = dynamodb.Table(os.environ["DISCOVERY_CONTROL_TABLE_NAME"])
    return table.get_item(Key={"pk": f"RUN#{run_id}", "sk": "RUN"})["Item"]


def test_planner_integration_seeds_added_spots_and_queues_scrapes(s3, monkeypatch, lambda_context):
    bucket = os.environ["S3_BUCKET_NAME"]
    run_id = "run-add"
    raw_key = "raw/sitemap/scrape_date=2026-05-01/discovery_run_id=run-add.json.gz"
    s3.put_object(
        Bucket=bucket,
        Key=raw_key,
        Body=gzip.compress(json.dumps({"spots": ["a", "b", "c"]}).encode()),
    )
    sqs = boto3.client("sqs", region_name="eu-west-2")
    spot_queue_url = sqs.create_queue(QueueName="planner-spot-scrapes")["QueueUrl"]
    batch_queue_url = sqs.create_queue(QueueName="planner-batch")["QueueUrl"]
    monkeypatch.setenv("DATA_BUCKET", bucket)
    monkeypatch.setenv("SPOT_SCRAPER_QUEUE_URL", spot_queue_url)
    monkeypatch.setenv("DISCOVERY_SPOT_BATCH_PROCESSOR_QUEUE_URL", batch_queue_url)
    monkeypatch.setattr("discovery_run_planner.handler._current_active_ids", lambda: {"b", "old"})

    response = lambda_handler(
        {
            "Records": [
                {
                    "body": json.dumps(
                        {
                            "discovery_run_id": run_id,
                            "scrape_date": "2026-05-01",
                            "raw_bucket": bucket,
                            "raw_key": raw_key,
                        }
                    )
                }
            ]
        },
        lambda_context,
    )

    assert response["statusCode"] == 200
    run = _run_item(run_id)
    assert run["status"] == "waiting_for_spot_scrapes"
    assert run["expected_spot_count"] == 2
    manifest_key = run["planner_manifest_key"]
    manifest = json.loads(s3.get_object(Bucket=bucket, Key=manifest_key)["Body"].read())
    assert manifest["added_spot_ids"] == ["a", "c"]
    assert manifest["removed_spot_ids"] == ["old"]
    messages = sorted(_queue_messages(spot_queue_url), key=lambda m: m["spot_id"])
    assert [m["spot_id"] for m in messages] == ["a", "c"]
    assert _queue_messages(batch_queue_url) == []


def test_planner_integration_removed_only_queues_batch_processor(s3, monkeypatch, lambda_context):
    bucket = os.environ["S3_BUCKET_NAME"]
    run_id = "run-removed"
    raw_key = "raw/sitemap/scrape_date=2026-05-01/discovery_run_id=run-removed.json.gz"
    s3.put_object(
        Bucket=bucket, Key=raw_key, Body=gzip.compress(json.dumps({"spots": ["a"]}).encode())
    )
    sqs = boto3.client("sqs", region_name="eu-west-2")
    spot_queue_url = sqs.create_queue(QueueName="removed-spot-scrapes")["QueueUrl"]
    batch_queue_url = sqs.create_queue(QueueName="removed-batch")["QueueUrl"]
    monkeypatch.setenv("DATA_BUCKET", bucket)
    monkeypatch.setenv("SPOT_SCRAPER_QUEUE_URL", spot_queue_url)
    monkeypatch.setenv("DISCOVERY_SPOT_BATCH_PROCESSOR_QUEUE_URL", batch_queue_url)
    monkeypatch.setattr("discovery_run_planner.handler._current_active_ids", lambda: {"a", "old"})

    lambda_handler(
        {
            "Records": [
                {
                    "body": json.dumps(
                        {
                            "discovery_run_id": run_id,
                            "scrape_date": "2026-05-01",
                            "raw_bucket": bucket,
                            "raw_key": raw_key,
                        }
                    )
                }
            ]
        },
        lambda_context,
    )

    run = _run_item(run_id)
    assert run["status"] == "spot_scrapes_complete"
    assert run["expected_spot_count"] == 0
    assert _queue_messages(spot_queue_url) == []
    batch_messages = _queue_messages(batch_queue_url)
    assert batch_messages == [
        {
            "schema_version": 1,
            "message_type": "discovery_spot_batch_process_requested",
            "discovery_run_id": run_id,
            "requested_at": batch_messages[0]["requested_at"],
        }
    ]
