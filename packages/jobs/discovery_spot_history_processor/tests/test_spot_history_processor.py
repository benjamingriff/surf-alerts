import gzip
import io
import json

import pyarrow.parquet as pq

from discovery_spot_history_processor.handler import lambda_handler


def _write_gzip_json(s3_client, bucket: str, key: str, body: dict) -> None:
    s3_client.put_object(
        Bucket=bucket,
        Key=key,
        Body=gzip.compress(json.dumps(body).encode("utf-8")),
        ContentType="application/json",
        ContentEncoding="gzip",
    )


def _event(bucket: str, key: str) -> dict:
    return {"detail": {"bucket": {"name": bucket}, "object": {"key": key}}}


def test_spot_history_processor_writes_bulk_history_and_catalog_manifest(s3, lambda_context):
    bucket = "dataeng-squeegee-test-bucket"
    sitemap_key = "raw/sitemap/scrape_date=2026-03-09/run_id=run-1.json.gz"
    raw_key = "raw/spot_report/spot_id=abc/scrape_date=2026-03-09/run_id=spot-1.json.gz"
    manifest_key = (
        "control/manifests/processing/domain=discovery/stage=spot_history/"
        "date=2026-03-09/discovery_run_id=run-1.json.gz"
    )

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
    _write_gzip_json(
        s3,
        bucket,
        manifest_key,
        {
            "schema_version": 1,
            "manifest_type": "processing_manifest",
            "domain": "discovery",
            "stage": "spot_history",
            "discovery_run_id": "run-1",
            "scrape_date": "2026-03-09",
            "source_manifest_key": "control/manifests/discovery_runs/date=2026-03-09/discovery_run_id=run-1/manifest.json.gz",
            "spot_ids": ["abc"],
            "raw_keys": [raw_key],
            "ready_at": "2026-03-09T06:10:00+00:00",
        },
    )

    response = lambda_handler(_event(bucket, manifest_key), lambda_context)

    assert response["statusCode"] == 200
    latest_core = pq.read_table(
        io.BytesIO(
            s3.get_object(
                Bucket=bucket,
                Key="processed/discovery/dim_spots_core/year=2026/month=03/discovery_run_id=run-1.parquet",
            )["Body"].read()
        )
    ).to_pylist()
    assert [row["spot_id"] for row in latest_core] == ["abc"]

    catalog_manifest = s3.get_object(
        Bucket=bucket,
        Key=(
            "control/manifests/processing/domain=discovery/stage=catalog_build/"
            "date=2026-03-09/discovery_run_id=run-1.json.gz"
        ),
    )
    assert catalog_manifest["ContentEncoding"] == "gzip"

