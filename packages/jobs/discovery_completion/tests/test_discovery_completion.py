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


def test_discovery_completion_emits_spot_history_manifest_when_expected_count_met(s3, lambda_context):
    bucket = "dataeng-squeegee-test-bucket"
    manifest_key = "control/manifests/discovery_runs/date=2026-03-09/discovery_run_id=run-1/manifest.json.gz"
    _write_json(
        s3,
        bucket,
        manifest_key,
        {
            "schema_version": 1,
            "manifest_type": "discovery_run",
            "discovery_run_id": "run-1",
            "sitemap_run_id": "run-1",
            "scrape_date": "2026-03-09",
            "source_type": "sitemap",
            "sitemap_raw_key": "raw/sitemap/scrape_date=2026-03-09/run_id=run-1.json.gz",
            "added_spot_ids": ["a", "b"],
            "added_spot_count": 2,
            "removed_spot_ids": [],
            "removed_count": 0,
            "created_at": "2026-03-09T06:00:00+00:00",
        },
    )
    _write_json(
        s3,
        bucket,
        "control/completions/discovery_spot_scrapes/date=2026-03-09/discovery_run_id=run-1/spot_id=a.json.gz",
        {"spot_id": "a", "raw_key": "raw/spot_report/spot_id=a/..."},
    )
    _write_json(
        s3,
        bucket,
        "control/completions/discovery_spot_scrapes/date=2026-03-09/discovery_run_id=run-1/spot_id=b.json.gz",
        {"spot_id": "b", "raw_key": "raw/spot_report/spot_id=b/..."},
    )

    response = lambda_handler(
        _event(
            bucket,
            "control/completions/discovery_spot_scrapes/date=2026-03-09/discovery_run_id=run-1/spot_id=b.json.gz",
        ),
        lambda_context,
    )

    assert response["statusCode"] == 200
    processing_manifest = s3.get_object(
        Bucket=bucket,
        Key=(
            "control/manifests/processing/domain=discovery/stage=spot_history/"
            "date=2026-03-09/discovery_run_id=run-1.json.gz"
        ),
    )
    assert processing_manifest["ContentEncoding"] == "gzip"


