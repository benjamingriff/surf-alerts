import gzip
import json

import pytest

from discovery_completion import handler as handler_module
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


def test_discovery_completion_emits_spot_history_manifest_when_expected_count_met(s3, monkeypatch, lambda_context):
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
        (
            "control/completions/discovery_spot_scrapes/date=2026-03-09/discovery_run_id=run-1/"
            "spot_id=a/raw_run_id=spot-run-a.json.gz"
        ),
        {"spot_id": "a", "raw_key": "raw/spot_report/spot_id=a/..."},
    )
    _write_json(
        s3,
        bucket,
        (
            "control/completions/discovery_spot_scrapes/date=2026-03-09/discovery_run_id=run-1/"
            "spot_id=b/raw_run_id=spot-run-b.json.gz"
        ),
        {"spot_id": "b", "raw_key": "raw/spot_report/spot_id=b/..."},
    )

    original_get_json = handler_module.s3_client.get_json

    def fail_on_new_success_marker(bucket_name: str, object_key: str):
        if "control/completions/discovery_spot_scrapes/" in object_key:
            raise AssertionError(f"unexpected success marker read: {object_key}")
        return original_get_json(bucket_name, object_key)

    monkeypatch.setattr("discovery_completion.handler.s3_client.get_json", fail_on_new_success_marker)

    response = lambda_handler(
        _event(
            bucket,
            (
                "control/completions/discovery_spot_scrapes/date=2026-03-09/discovery_run_id=run-1/"
                "spot_id=b/raw_run_id=spot-run-b.json.gz"
            ),
        ),
        lambda_context,
    )
    assert response["statusCode"] == 200
    processing_manifest = json.loads(
        gzip.decompress(
            s3.get_object(
                Bucket=bucket,
                Key=(
                    "control/manifests/processing/domain=discovery/stage=spot_history/"
                    "date=2026-03-09/discovery_run_id=run-1.json.gz"
                ),
            )["Body"].read()
        ).decode("utf-8")
    )
    assert processing_manifest["raw_keys"] == [
        "raw/spot_report/spot_id=a/scrape_date=2026-03-09/run_id=spot-run-a.json.gz",
        "raw/spot_report/spot_id=b/scrape_date=2026-03-09/run_id=spot-run-b.json.gz",
    ]


def test_discovery_completion_emits_manifest_when_terminal_success_and_failure_count_met(s3, lambda_context):
    bucket = "dataeng-squeegee-test-bucket"
    manifest_key = "control/manifests/discovery_runs/date=2026-03-09/discovery_run_id=run-2/manifest.json.gz"
    _write_json(
        s3,
        bucket,
        manifest_key,
        {
            "schema_version": 1,
            "manifest_type": "discovery_run",
            "discovery_run_id": "run-2",
            "sitemap_run_id": "run-2",
            "scrape_date": "2026-03-09",
            "source_type": "sitemap",
            "sitemap_raw_key": "raw/sitemap/scrape_date=2026-03-09/run_id=run-2.json.gz",
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
        (
            "control/completions/discovery_spot_scrapes/date=2026-03-09/discovery_run_id=run-2/"
            "spot_id=a/raw_run_id=spot-run-a.json.gz"
        ),
        {"spot_id": "a", "raw_key": "raw/spot_report/spot_id=a/..."},
    )
    _write_json(
        s3,
        bucket,
        "control/completions/discovery_spot_scrapes_failed/date=2026-03-09/discovery_run_id=run-2/spot_id=b.json.gz",
        {
            "spot_id": "b",
            "failure_reason": "scrape_failed_after_max_retries",
            "failure_source": "spot_scraper_dlq",
            "completed_at": "2026-03-09T06:06:00+00:00",
        },
    )

    response = lambda_handler(
        _event(
            bucket,
            "control/completions/discovery_spot_scrapes_failed/date=2026-03-09/discovery_run_id=run-2/spot_id=b.json.gz",
        ),
        lambda_context,
    )

    assert response["statusCode"] == 200
    processing_manifest = json.loads(
        gzip.decompress(
            s3.get_object(
                Bucket=bucket,
                Key=(
                    "control/manifests/processing/domain=discovery/stage=spot_history/"
                    "date=2026-03-09/discovery_run_id=run-2.json.gz"
                ),
            )["Body"].read()
        ).decode("utf-8")
    )
    assert processing_manifest["spot_ids"] == ["a"]
    assert processing_manifest["raw_keys"] == [
        "raw/spot_report/spot_id=a/scrape_date=2026-03-09/run_id=spot-run-a.json.gz"
    ]
    assert processing_manifest["failed_spot_ids"] == ["b"]
    assert processing_manifest["failed_spot_count"] == 1


def test_discovery_completion_fails_on_legacy_success_marker_key(s3, lambda_context):
    bucket = "dataeng-squeegee-test-bucket"
    manifest_key = "control/manifests/discovery_runs/date=2026-03-09/discovery_run_id=run-legacy/manifest.json.gz"
    _write_json(
        s3,
        bucket,
        manifest_key,
        {
            "schema_version": 1,
            "manifest_type": "discovery_run",
            "discovery_run_id": "run-legacy",
            "sitemap_run_id": "run-legacy",
            "scrape_date": "2026-03-09",
            "source_type": "sitemap",
            "sitemap_raw_key": "raw/sitemap/scrape_date=2026-03-09/run_id=run-legacy.json.gz",
            "added_spot_ids": ["legacy"],
            "added_spot_count": 1,
            "removed_spot_ids": [],
            "removed_count": 0,
            "created_at": "2026-03-09T06:00:00+00:00",
        },
    )
    _write_json(
        s3,
        bucket,
        "control/completions/discovery_spot_scrapes/date=2026-03-09/discovery_run_id=run-legacy/spot_id=legacy.json.gz",
        {"spot_id": "legacy", "raw_key": "raw/spot_report/spot_id=legacy/legacy.json.gz"},
    )

    with pytest.raises(ValueError, match="Unsupported legacy discovery success marker key"):
        lambda_handler(
            _event(
                bucket,
                "control/completions/discovery_spot_scrapes/date=2026-03-09/discovery_run_id=run-legacy/spot_id=legacy.json.gz",
            ),
            lambda_context,
        )

    objects = s3.list_objects_v2(
        Bucket=bucket,
        Prefix="control/manifests/processing/domain=discovery/stage=spot_history/date=2026-03-09/",
    )
    assert "Contents" not in objects
