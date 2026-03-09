import gzip
import io
import json

import pyarrow as pa
import pyarrow.parquet as pq

from spot_report_processor.handler import _canonicalize_spot, _checksum, lambda_handler


def _write_gzip_json(s3_client, bucket: str, key: str, body: dict) -> None:
    s3_client.put_object(
        Bucket=bucket,
        Key=key,
        Body=gzip.compress(json.dumps(body).encode("utf-8")),
        ContentType="application/json",
        ContentEncoding="gzip",
    )


def _write_parquet(s3_client, bucket: str, key: str, rows: list[dict]) -> None:
    buffer = io.BytesIO()
    pq.write_table(pa.Table.from_pylist(rows), buffer, compression="snappy")
    s3_client.put_object(Bucket=bucket, Key=key, Body=buffer.getvalue())


def _event(bucket: str, key: str) -> dict:
    return {"detail": {"bucket": {"name": bucket}, "object": {"key": key}}}


def test_spot_report_processor_writes_added_version_rows(s3, lambda_context):
    bucket = "dataeng-squeegee-test-bucket"
    raw_key = "raw/spot_report/spot_id=abc/scrape_date=2026-03-09/run_id=spot-1.json.gz"
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
            "discovery_run_id": "discovery-1",
            "sitemap_run_id": "sitemap-1",
            "source_raw_key": None,
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

    response = lambda_handler(_event(bucket, raw_key), lambda_context)

    assert response["statusCode"] == 200
    completion = s3.get_object(
        Bucket=bucket,
        Key="control/manifests/discovery_runs/date=2026-03-09/run_id=discovery-1/completed/spot_id=abc.json.gz",
    )
    assert completion["ContentEncoding"] == "gzip"

    listing = s3.list_objects_v2(Bucket=bucket, Prefix="processed/discovery/dim_spots_core/")
    parquet_keys = [item["Key"] for item in listing["Contents"] if item["Key"].endswith(".parquet")]
    table = pq.read_table(io.BytesIO(s3.get_object(Bucket=bucket, Key=parquet_keys[0])["Body"].read()))
    row = table.to_pylist()[0]
    assert row["spot_id"] == "abc"
    assert row["event_type"] == "added"


def test_spot_report_processor_skips_unchanged_payload(s3, lambda_context):
    bucket = "dataeng-squeegee-test-bucket"
    raw_payload = {
        "spot": {"name": "Rest Bay", "lat": 51.0, "lon": -3.0, "breadcrumb": [], "cameras": []},
        "associated": {"timezone": "Europe/London", "utcOffset": 0, "abbrTimezone": "GMT"},
    }
    checksum = _checksum(_canonicalize_spot(raw_payload, "abc"))
    _write_parquet(
        s3,
        bucket,
        "processed/discovery/catalog_latest/dim_spots_core.parquet",
        [
            {
                "spot_version_id": "latest-1",
                "spot_id": "abc",
                "version_ts": "2026-03-08T06:00:00+00:00",
                "content_checksum": checksum,
                "event_type": "added",
                "seen_at": "2026-03-08T06:00:00+00:00",
                "sitemap_link": None,
                "forecast_link": None,
                "source_run_id": "prev",
                "source_raw_key": "raw/spot_report/prev",
                "source_type": "spot_report",
                "schema_version": 1,
                "processed_at": "2026-03-08T06:00:01+00:00",
            }
        ],
    )

    raw_key = "raw/spot_report/spot_id=abc/scrape_date=2026-03-09/run_id=spot-2.json.gz"
    _write_gzip_json(
        s3,
        bucket,
        raw_key,
        {
            "schema_version": 1,
            "run_id": "spot-2",
            "source_type": "spot_report",
            "produced_at": "2026-03-09T06:05:00Z",
            "scraped_at": "2026-03-09T06:05:00Z",
            "spot_id": "abc",
            "discovery_run_id": None,
            "sitemap_run_id": None,
            "source_raw_key": None,
            "requested_at": None,
            "raw_payload": raw_payload,
        },
    )

    lambda_handler(_event(bucket, raw_key), lambda_context)

    listing = s3.list_objects_v2(Bucket=bucket, Prefix="processed/discovery/dim_spots_core/")
    assert listing["KeyCount"] == 0
