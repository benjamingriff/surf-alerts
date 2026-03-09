import gzip
import io
import json

import pyarrow as pa
import pyarrow.parquet as pq

from discovery_catalog_builder.handler import lambda_handler


def _write_json(s3_client, bucket: str, key: str, body: dict) -> None:
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


def test_catalog_builder_rebuilds_latest_snapshot_from_history(s3, lambda_context):
    bucket = "dataeng-squeegee-test-bucket"
    manifest_key = (
        "control/manifests/processing/domain=discovery/stage=catalog_build/"
        "date=2026-03-09/discovery_run_id=run-1.json.gz"
    )
    _write_json(
        s3,
        bucket,
        manifest_key,
        {
            "schema_version": 1,
            "manifest_type": "processing_manifest",
            "domain": "discovery",
            "stage": "catalog_build",
            "discovery_run_id": "run-1",
            "scrape_date": "2026-03-09",
            "source_manifest_key": "control/manifests/processing/domain=discovery/stage=spot_history/date=2026-03-09/discovery_run_id=run-1.json.gz",
            "source_keys": [],
            "ready_at": "2026-03-09T06:10:00+00:00",
        },
    )
    _write_parquet(
        s3,
        bucket,
        "processed/discovery/dim_spots_core/year=2026/month=03/discovery_run_id=run-0.parquet",
        [
            {
                "spot_version_id": "v1",
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
            },
            {
                "spot_version_id": "v2",
                "spot_id": "b",
                "version_ts": "2026-03-09T06:02:00+00:00",
                "content_checksum": None,
                "event_type": "removed",
                "seen_at": "2026-03-09T06:02:00+00:00",
                "sitemap_link": "https://example.com/b",
                "forecast_link": None,
                "source_run_id": "sitemap-1",
                "source_raw_key": "raw/sitemap/b",
                "source_type": "sitemap",
                "schema_version": 1,
                "processed_at": "2026-03-09T06:02:01+00:00",
            },
        ],
    )
    _write_parquet(
        s3,
        bucket,
        "processed/discovery/dim_spot_location/year=2026/month=03/discovery_run_id=run-0.parquet",
        [
            {
                "spot_version_id": "v1",
                "spot_id": "a",
                "name": "Rest Bay",
                "lat": 51.0,
                "lon": -3.0,
                "timezone": "Europe/London",
                "utc_offset": 0,
                "abbr_timezone": "GMT",
                "subregion_id": None,
                "subregion_name": "Wales",
            }
        ],
    )

    response = lambda_handler(_event(bucket, manifest_key), lambda_context)

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

