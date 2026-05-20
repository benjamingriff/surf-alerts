import gzip
import io
import json
import os

import boto3
import pyarrow.parquet as pq

from discovery_control import ControlStore
from discovery_spot_history_processor.handler import lambda_handler


def _write_gzip_json(s3_client, bucket: str, key: str, body: dict) -> None:
    s3_client.put_object(
        Bucket=bucket,
        Key=key,
        Body=gzip.compress(json.dumps(body).encode("utf-8")),
        ContentType="application/json",
        ContentEncoding="gzip",
    )


def _control_store():
    dynamodb = boto3.resource("dynamodb", region_name="eu-west-2")
    return ControlStore(
        table_name=os.environ["DISCOVERY_CONTROL_TABLE_NAME"],
        dynamodb_resource=dynamodb,
    )


def test_spot_history_worker_writes_chunk_history_and_queues_catalog_build(s3, monkeypatch, lambda_context):
    bucket = "dataeng-squeegee-test-bucket"
    monkeypatch.setenv("DATA_BUCKET", bucket)
    sqs_client = boto3.client("sqs", region_name="eu-west-2")
    catalog_queue_url = sqs_client.create_queue(QueueName="catalog-build-worker")["QueueUrl"]
    monkeypatch.setenv("DISCOVERY_CATALOG_BUILD_QUEUE_URL", catalog_queue_url)

    sitemap_key = "raw/sitemap/scrape_date=2026-03-09/run_id=run-1.json.gz"
    raw_key = "raw/spot_report/spot_id=abc/scrape_date=2026-03-09/run_id=spot-1.json.gz"

    _write_gzip_json(
        s3,
        bucket,
        sitemap_key,
        {
            "spots": {
                "abc": {
                    "spot_id": "abc",
                    "link": "https://example.com/abc",
                    "forecast": "https://example.com/abc/forecast",
                }
            }
        },
    )
    _write_gzip_json(
        s3,
        bucket,
        raw_key,
        {
            "schema_version": 1,
            "run_id": "spot-1",
            "source_type": "spot_report",
            "produced_at": "2026-03-09T06:05:00Z",
            "scraped_at": "2026-03-09T06:05:00Z",
            "spot_id": "abc",
            "discovery_run_id": "run-1",
            "sitemap_run_id": "run-1",
            "source_raw_key": sitemap_key,
            "requested_at": "2026-03-09T06:04:00Z",
            "raw_payload": {
                "spot": {
                    "name": "Rest Bay",
                    "lat": 51.0,
                    "lon": -3.0,
                    "breadcrumb": [{"name": "Europe", "href": "/europe"}],
                    "cameras": [],
                    "abilityLevels": ["BEGINNER"],
                    "boardTypes": ["LONGBOARD"],
                    "travelDetails": {"description": "desc", "best": {}, "bottom": {"value": []}},
                },
                "associated": {"timezone": "Europe/London", "utcOffset": 0, "abbrTimezone": "GMT"},
            },
        },
    )

    store = _control_store()
    store.seed_run(
        discovery_run_id="run-1",
        scrape_date="2026-03-09",
        sitemap_raw_key=sitemap_key,
        expected_spot_count=1,
        removed_spot_ids=[],
    )
    assert store.transition_run_status(
        discovery_run_id="run-1",
        from_status="waiting_for_spot_scrapes",
        to_status="spot_history_in_progress",
    )
    store.create_chunks(
        discovery_run_id="run-1",
        chunks=[{"chunk_id": "chunk-0001", "spot_ids": ["abc"], "raw_keys": [raw_key]}],
    )

    response = lambda_handler(
        {"Records": [{"body": json.dumps({"discovery_run_id": "run-1", "chunk_id": "chunk-0001"})}]},
        lambda_context,
    )

    assert response["statusCode"] == 200
    latest_core = pq.read_table(
        io.BytesIO(
            s3.get_object(
                Bucket=bucket,
                Key="processed/discovery/dim_spots_core/year=2026/month=03/discovery_run_id=run-1/chunk_id=chunk-0001.parquet",
            )["Body"].read()
        )
    ).to_pylist()
    assert [row["spot_id"] for row in latest_core] == ["abc"]

    run = store.get_run("run-1")
    assert run["status"] == "catalog_build_ready"
    message = sqs_client.receive_message(QueueUrl=catalog_queue_url, MaxNumberOfMessages=1)["Messages"][0]
    assert json.loads(message["Body"]) == {"discovery_run_id": "run-1"}
