import gzip
import json

from discovery_completion.handler import lambda_handler


def _write_json(s3_client, bucket: str, key: str, body: dict) -> None:
    s3_client.put_object(
        Bucket=bucket,
        Key=key,
        Body=gzip.compress(json.dumps(body).encode("utf-8")),
        ContentType="application/json",
        ContentEncoding="gzip",
    )


def _event(bucket: str, key: str) -> dict:
    return {"detail": {"bucket": {"name": bucket}, "object": {"key": key}}}


def test_discovery_completion_emits_processing_manifest_when_expected_count_met(s3, lambda_context):
    bucket = "dataeng-squeegee-test-bucket"
    manifest_key = "control/manifests/discovery_runs/date=2026-03-09/run_id=run-1.json.gz"
    _write_json(
        s3,
        bucket,
        manifest_key,
        {
            "schema_version": 1,
            "discovery_run_id": "run-1",
            "sitemap_run_id": "run-1",
            "scrape_date": "2026-03-09",
            "source_type": "sitemap",
            "sitemap_raw_key": "raw/sitemap/scrape_date=2026-03-09/run_id=run-1.json.gz",
            "expected_spot_ids": ["a", "b"],
            "expected_count": 2,
            "removed_spot_ids": [],
            "removed_count": 0,
            "created_at": "2026-03-09T06:00:00+00:00",
            "catalog_ready_at": None,
            "processing_manifest_key": (
                "control/manifests/processing/domain=discovery/date=2026-03-09/run_id=run-1.json.gz"
            ),
        },
    )
    _write_json(
        s3,
        bucket,
        "control/manifests/discovery_runs/date=2026-03-09/run_id=run-1/completed/spot_id=a.json.gz",
        {"raw_key": "raw/spot_report/spot_id=a/..."},
    )
    _write_json(
        s3,
        bucket,
        "control/manifests/discovery_runs/date=2026-03-09/run_id=run-1/completed/spot_id=b.json.gz",
        {"raw_key": "raw/spot_report/spot_id=b/..."},
    )

    response = lambda_handler(
        _event(
            bucket,
            "control/manifests/discovery_runs/date=2026-03-09/run_id=run-1/completed/spot_id=b.json.gz",
        ),
        lambda_context,
    )

    assert response["statusCode"] == 200
    processing_manifest = s3.get_object(
        Bucket=bucket,
        Key="control/manifests/processing/domain=discovery/date=2026-03-09/run_id=run-1.json.gz",
    )
    assert processing_manifest["ContentEncoding"] == "gzip"
