import gzip
import json
import os

import boto3

from spot_scraper.handler import lambda_handler


def test_spot_scraper_writes_raw_report_and_enqueues_completion(s3, monkeypatch, lambda_context):
    bucket = os.environ["S3_BUCKET_NAME"]
    sqs_client = boto3.client("sqs", region_name="eu-west-2")
    completion_queue_url = sqs_client.create_queue(QueueName="discovery-completion")["QueueUrl"]
    monkeypatch.setenv("DATA_BUCKET", bucket)
    monkeypatch.setenv("DISCOVERY_COMPLETION_QUEUE_URL", completion_queue_url)
    monkeypatch.setattr(
        "spot_scraper.handler._fetch_spot_report",
        lambda spot_id: {
            "spot": {"name": f"Spot {spot_id}", "lat": 51.0, "lon": -3.0},
            "associated": {"timezone": "Europe/London", "utcOffset": 0, "abbrTimezone": "GMT"},
        },
    )
    monkeypatch.setattr("spot_scraper.handler._utc_now_iso", lambda: "2026-03-09T06:02:00Z")

    response = lambda_handler(
        {
            "Records": [
                {
                    "body": json.dumps(
                        {
                            "schema_version": 1,
                            "message_type": "spot_scrape_requested",
                            "spot_id": "abc",
                            "discovery_run_id": "run-1",
                            "scrape_date": "2026-03-09",
                            "sitemap_raw_key": "raw/sitemap/scrape_date=2026-03-09/discovery_run_id=run-1.json.gz",
                            "requested_at": "2026-03-09T06:00:00Z",
                        }
                    )
                }
            ]
        },
        lambda_context,
    )

    assert response["statusCode"] == 200

    key = "raw/spot_report/scrape_date=2026-03-09/discovery_run_id=run-1/spot_id=abc.json.gz"
    raw_object = s3.get_object(Bucket=bucket, Key=key)
    payload = json.loads(gzip.decompress(raw_object["Body"].read()))
    assert payload["spot_id"] == "abc"
    assert payload["discovery_run_id"] == "run-1"
    assert payload["source_type"] == "spot_report"

    message = sqs_client.receive_message(QueueUrl=completion_queue_url, MaxNumberOfMessages=1)[
        "Messages"
    ][0]
    completion_payload = json.loads(message["Body"])
    assert completion_payload["discovery_run_id"] == "run-1"
    assert completion_payload["spot_id"] == "abc"
    assert completion_payload["terminal_status"] == "success"
    assert completion_payload["raw_key"] == key
