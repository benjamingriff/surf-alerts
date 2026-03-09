import io
import json

import boto3
import pyarrow as pa
import pyarrow.parquet as pq

from discovery_diff.handler import lambda_handler


def _write_gzip_json(s3_client, bucket: str, key: str, body: dict) -> None:
    import gzip

    payload = gzip.compress(json.dumps(body).encode("utf-8"))
    s3_client.put_object(
        Bucket=bucket,
        Key=key,
        Body=payload,
        ContentType="application/json",
        ContentEncoding="gzip",
    )


def _write_parquet(s3_client, bucket: str, key: str, rows: list[dict]) -> None:
    table = pa.Table.from_pylist(rows)
    buffer = io.BytesIO()
    pq.write_table(table, buffer, compression="snappy")
    s3_client.put_object(Bucket=bucket, Key=key, Body=buffer.getvalue())


def _event(bucket: str, key: str) -> dict:
    return {"detail": {"bucket": {"name": bucket}, "object": {"key": key}}}


def test_discovery_diff_enqueues_added_spots_and_writes_manifest(s3, monkeypatch, lambda_context):
    bucket = "dataeng-squeegee-test-bucket"
    sqs_client = boto3.client("sqs", region_name="eu-west-2")
    queue_url = sqs_client.create_queue(QueueName="spot-scraper")["QueueUrl"]
    monkeypatch.setenv("SPOT_SCRAPER_QUEUE_URL", queue_url)

    key = "raw/sitemap/scrape_date=2026-03-09/run_id=sitemap-1.json.gz"
    _write_gzip_json(
        s3,
        bucket,
        key,
        {
            "schema_version": 1,
            "run_id": "sitemap-1",
            "source_type": "sitemap",
            "produced_at": "2026-03-09T06:00:00+00:00",
            "scraped_at": "2026-03-09T06:00:00+00:00",
            "spot_count": 2,
            "spots": {
                "a": {"spot_id": "a", "link": "https://example.com/a", "forecast": None},
                "b": {"spot_id": "b", "link": "https://example.com/b", "forecast": None},
            },
        },
    )

    response = lambda_handler(_event(bucket, key), lambda_context)

    assert response["statusCode"] == 200
    manifest = s3.get_object(
        Bucket=bucket,
        Key="control/manifests/discovery_runs/date=2026-03-09/discovery_run_id=sitemap-1/manifest.json.gz",
    )
    assert manifest["ContentEncoding"] == "gzip"

    messages = sqs_client.receive_message(QueueUrl=queue_url, MaxNumberOfMessages=10)["Messages"]
    queued_spot_ids = sorted(json.loads(message["Body"])["spot_id"] for message in messages)
    assert queued_spot_ids == ["a", "b"]


def test_discovery_diff_removed_only_emits_catalog_build_manifest(s3, monkeypatch, lambda_context):
    bucket = "dataeng-squeegee-test-bucket"
    sqs_client = boto3.client("sqs", region_name="eu-west-2")
    queue_url = sqs_client.create_queue(QueueName="spot-scraper-removed")["QueueUrl"]
    monkeypatch.setenv("SPOT_SCRAPER_QUEUE_URL", queue_url)

    _write_parquet(
        s3,
        bucket,
        "processed/discovery/catalog_latest/dim_spots_core.parquet",
        [
            {
                "spot_version_id": "v1",
                "spot_id": "gone",
                "version_ts": "2026-03-08T06:00:00+00:00",
                "content_checksum": "abc",
                "event_type": "added",
                "seen_at": "2026-03-08T06:00:00+00:00",
                "sitemap_link": "https://example.com/gone",
                "forecast_link": None,
                "source_run_id": "prev",
                "source_raw_key": "raw/spot_report/spot_id=gone/...",
                "source_type": "spot_report",
                "schema_version": 1,
                "processed_at": "2026-03-08T06:01:00+00:00",
            }
        ],
    )

    key = "raw/sitemap/scrape_date=2026-03-09/run_id=sitemap-2.json.gz"
    _write_gzip_json(
        s3,
        bucket,
        key,
        {
            "schema_version": 1,
            "run_id": "sitemap-2",
            "source_type": "sitemap",
            "produced_at": "2026-03-09T06:00:00+00:00",
            "scraped_at": "2026-03-09T06:00:00+00:00",
            "spot_count": 0,
            "spots": {},
        },
    )

    lambda_handler(_event(bucket, key), lambda_context)

    manifest = s3.get_object(
        Bucket=bucket,
        Key=(
            "control/manifests/processing/domain=discovery/stage=catalog_build/"
            "date=2026-03-09/discovery_run_id=sitemap-2.json.gz"
        ),
    )
    assert manifest["ContentEncoding"] == "gzip"


