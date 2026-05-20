import io
import json
import os

import boto3
import pyarrow as pa
import pyarrow.parquet as pq

from discovery_catalog_builder.handler import lambda_handler
from discovery_control import ControlStore


def _write_parquet(s3_client, bucket: str, key: str, rows: list[dict]) -> None:
    buffer = io.BytesIO()
    pq.write_table(pa.Table.from_pylist(rows), buffer, compression="snappy")
    s3_client.put_object(Bucket=bucket, Key=key, Body=buffer.getvalue())


def _control_store():
    dynamodb = boto3.resource("dynamodb", region_name="eu-west-2")
    return ControlStore(
        table_name=os.environ["DISCOVERY_CONTROL_TABLE_NAME"],
        dynamodb_resource=dynamodb,
    )


def test_catalog_builder_rebuilds_latest_snapshot_incrementally(s3, monkeypatch, lambda_context):
    bucket = "dataeng-squeegee-test-bucket"
    monkeypatch.setenv("DATA_BUCKET", bucket)
    store = _control_store()
    store.seed_run(
        discovery_run_id="run-1",
        scrape_date="2026-03-09",
        sitemap_raw_key="raw/sitemap/scrape_date=2026-03-09/run_id=run-1.json.gz",
        expected_spot_count=1,
        removed_spot_ids=["b"],
    )
    store.seed_spots(discovery_run_id="run-1", spot_ids=["a"])
    store.mark_spot_terminal(
        discovery_run_id="run-1",
        spot_id="a",
        terminal_status="success",
        raw_key="raw/spot_report/a.json.gz",
        completed_at="2026-03-09T06:00:00Z",
    )
    assert store.transition_run_status(
        discovery_run_id="run-1",
        from_status="waiting_for_spot_scrapes",
        to_status="catalog_build_ready",
    )
    store.create_chunks(
        discovery_run_id="run-1",
        chunks=[{"chunk_id": "chunk-0001", "spot_ids": ["a"], "raw_keys": ["raw/spot_report/a.json.gz"]}],
    )
    store.mark_chunk_complete(
        discovery_run_id="run-1",
        chunk_id="chunk-0001",
        output_keys=[
            "processed/discovery/dim_spots_core/year=2026/month=03/discovery_run_id=run-1/chunk_id=chunk-0001.parquet",
            "processed/discovery/dim_spot_location/year=2026/month=03/discovery_run_id=run-1/chunk_id=chunk-0001.parquet",
        ],
    )
    assert store.transition_run_status(
        discovery_run_id="run-1",
        from_status="spot_history_in_progress",
        to_status="catalog_build_ready",
    )

    _write_parquet(
        s3,
        bucket,
        "processed/discovery/catalog_latest/dim_spots_core.parquet",
        [
            {
                "spot_version_id": "old-a",
                "spot_id": "a",
                "version_ts": "2026-03-08T06:01:00+00:00",
                "content_checksum": None,
                "event_type": "added",
                "seen_at": "2026-03-08T06:01:00+00:00",
                "sitemap_link": "https://example.com/a-old",
                "forecast_link": None,
                "source_run_id": "old",
                "source_raw_key": "raw/spot_report/a-old",
                "source_type": "spot_report",
                "schema_version": 1,
                "processed_at": "2026-03-08T06:01:01+00:00",
            },
            {
                "spot_version_id": "old-b",
                "spot_id": "b",
                "version_ts": "2026-03-08T06:01:00+00:00",
                "content_checksum": None,
                "event_type": "added",
                "seen_at": "2026-03-08T06:01:00+00:00",
                "sitemap_link": "https://example.com/b",
                "forecast_link": None,
                "source_run_id": "old",
                "source_raw_key": "raw/spot_report/b-old",
                "source_type": "spot_report",
                "schema_version": 1,
                "processed_at": "2026-03-08T06:01:01+00:00",
            },
        ],
    )
    _write_parquet(
        s3,
        bucket,
        "processed/discovery/catalog_latest/dim_spot_location.parquet",
        [
            {
                "spot_version_id": "old-a",
                "spot_id": "a",
                "name": "Old A",
                "lat": 1.0,
                "lon": 1.0,
                "timezone": "UTC",
                "utc_offset": 0,
                "abbr_timezone": "UTC",
                "subregion_id": None,
                "subregion_name": None,
            },
            {
                "spot_version_id": "old-b",
                "spot_id": "b",
                "name": "Old B",
                "lat": 2.0,
                "lon": 2.0,
                "timezone": "UTC",
                "utc_offset": 0,
                "abbr_timezone": "UTC",
                "subregion_id": None,
                "subregion_name": None,
            },
        ],
    )
    _write_parquet(
        s3,
        bucket,
        "processed/discovery/dim_spots_core/year=2026/month=03/discovery_run_id=run-1/chunk_id=chunk-0001.parquet",
        [
            {
                "spot_version_id": "new-a",
                "spot_id": "a",
                "version_ts": "2026-03-09T06:01:00+00:00",
                "content_checksum": None,
                "event_type": "added",
                "seen_at": "2026-03-09T06:01:00+00:00",
                "sitemap_link": "https://example.com/a",
                "forecast_link": None,
                "source_run_id": "spot-1",
                "source_raw_key": "raw/spot_report/a",
                "source_type": "spot_report",
                "schema_version": 1,
                "processed_at": "2026-03-09T06:01:01+00:00",
            }
        ],
    )
    _write_parquet(
        s3,
        bucket,
        "processed/discovery/dim_spot_location/year=2026/month=03/discovery_run_id=run-1/chunk_id=chunk-0001.parquet",
        [
            {
                "spot_version_id": "new-a",
                "spot_id": "a",
                "name": "New A",
                "lat": 3.0,
                "lon": 3.0,
                "timezone": "UTC",
                "utc_offset": 0,
                "abbr_timezone": "UTC",
                "subregion_id": None,
                "subregion_name": None,
            }
        ],
    )

    response = lambda_handler(
        {"Records": [{"body": json.dumps({"discovery_run_id": "run-1"})}]},
        lambda_context,
    )

    assert response["statusCode"] == 200
    latest_core = pq.read_table(
        io.BytesIO(
            s3.get_object(
                Bucket=bucket,
                Key="processed/discovery/catalog_latest/dim_spots_core.parquet",
            )["Body"].read()
        )
    ).to_pylist()
    assert [row["spot_id"] for row in latest_core] == ["a"]
    assert latest_core[0]["spot_version_id"] == "new-a"
