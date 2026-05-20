import gzip
import json
import os

import boto3

from spot_scraper.handler import lambda_handler


def _completion_messages(queue_url: str) -> list[dict]:
    sqs = boto3.client("sqs", region_name="eu-west-2")
    messages = sqs.receive_message(QueueUrl=queue_url, MaxNumberOfMessages=10).get("Messages", [])
    return [json.loads(message["Body"]) for message in messages]


def test_lambda_writes_gzipped_raw_report_and_success_completion(s3, monkeypatch, lambda_context):
    bucket = os.environ["S3_BUCKET_NAME"]
    sqs = boto3.client("sqs", region_name="eu-west-2")
    completion_queue_url = sqs.create_queue(QueueName="spot-completion-success")["QueueUrl"]
    monkeypatch.setenv("DATA_BUCKET", bucket)
    monkeypatch.setenv("DISCOVERY_COMPLETION_QUEUE_URL", completion_queue_url)
    monkeypatch.setattr(
        "spot_scraper.handler._fetch_spot_report", lambda spot_id: {"spot": {"name": "Spot A"}}
    )
    monkeypatch.setattr("spot_scraper.handler._utc_now_iso", lambda: "2026-05-01T06:02:10Z")

    response = lambda_handler(
        {
            "Records": [
                {
                    "body": json.dumps(
                        {
                            "discovery_run_id": "run-123",
                            "scrape_date": "2026-05-01",
                            "spot_id": "spot-a",
                            "sitemap_raw_key": "raw/sitemap/x.json.gz",
                            "requested_at": "2026-05-01T06:01:00Z",
                        }
                    )
                }
            ]
        },
        lambda_context,
    )

    assert response["statusCode"] == 200
    key = "raw/spot_report/scrape_date=2026-05-01/discovery_run_id=run-123/spot_id=spot-a.json.gz"
    obj = s3.get_object(Bucket=bucket, Key=key)
    assert obj["ContentEncoding"] == "gzip"
    payload = json.loads(gzip.decompress(obj["Body"].read()))
    assert payload["source_type"] == "spot_report"
    assert payload["spot_id"] == "spot-a"
    assert payload["discovery_run_id"] == "run-123"
    assert payload["source_raw_key"] == "raw/sitemap/x.json.gz"
    assert payload["raw_payload"] == {"spot": {"name": "Spot A"}}
    messages = _completion_messages(completion_queue_url)
    assert messages == [
        {
            "schema_version": 1,
            "message_type": "spot_scrape_complete",
            "terminal_status": "success",
            "discovery_run_id": "run-123",
            "scrape_date": "2026-05-01",
            "spot_id": "spot-a",
            "raw_bucket": bucket,
            "raw_key": key,
            "completed_at": "2026-05-01T06:02:10Z",
        }
    ]


def test_lambda_existing_raw_report_does_not_fetch_or_overwrite(s3, monkeypatch, lambda_context):
    bucket = os.environ["S3_BUCKET_NAME"]
    key = "raw/spot_report/scrape_date=2026-05-01/discovery_run_id=run-123/spot_id=spot-a.json.gz"
    original = {"already": "there"}
    s3.put_object(
        Bucket=bucket,
        Key=key,
        Body=gzip.compress(json.dumps(original).encode()),
        ContentEncoding="gzip",
    )
    sqs = boto3.client("sqs", region_name="eu-west-2")
    completion_queue_url = sqs.create_queue(QueueName="spot-completion-existing")["QueueUrl"]
    monkeypatch.setenv("DATA_BUCKET", bucket)
    monkeypatch.setenv("DISCOVERY_COMPLETION_QUEUE_URL", completion_queue_url)
    monkeypatch.setattr(
        "spot_scraper.handler._fetch_spot_report",
        lambda spot_id: (_ for _ in ()).throw(AssertionError("should not fetch")),
    )
    monkeypatch.setattr("spot_scraper.handler._utc_now_iso", lambda: "2026-05-01T06:02:10Z")

    lambda_handler(
        {
            "Records": [
                {
                    "body": json.dumps(
                        {
                            "discovery_run_id": "run-123",
                            "scrape_date": "2026-05-01",
                            "spot_id": "spot-a",
                        }
                    )
                }
            ]
        },
        lambda_context,
    )

    payload = json.loads(gzip.decompress(s3.get_object(Bucket=bucket, Key=key)["Body"].read()))
    assert payload == original
    messages = _completion_messages(completion_queue_url)
    assert messages[0]["terminal_status"] == "success"
    assert messages[0]["raw_key"] == key
