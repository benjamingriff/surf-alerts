import gzip
import json

from discovery_failure_finalizer.handler import lambda_handler


def test_failure_finalizer_writes_failed_marker(s3, monkeypatch, lambda_context):
    bucket = "dataeng-squeegee-test-bucket"
    monkeypatch.setenv("DATA_BUCKET", bucket)

    response = lambda_handler(
        {
            "Records": [
                {
                    "messageId": "msg-1",
                    "body": json.dumps(
                        {
                            "spot_id": "abc",
                            "discovery_run_id": "run-1",
                            "sitemap_run_id": "run-1",
                            "source_raw_key": "raw/sitemap/scrape_date=2026-03-09/run_id=run-1.json.gz",
                            "requested_at": "2026-03-09T06:00:00Z",
                        }
                    ),
                    "attributes": {"ApproximateReceiveCount": "4"},
                }
            ]
        },
        lambda_context,
    )

    assert response["statusCode"] == 200

    objects = s3.list_objects_v2(
        Bucket=bucket,
        Prefix="control/completions/discovery_spot_scrapes_failed/date=2026-03-09/",
    )["Contents"]
    assert len(objects) == 1

    payload = json.loads(
        gzip.decompress(s3.get_object(Bucket=bucket, Key=objects[0]["Key"])["Body"].read()).decode("utf-8")
    )
    assert payload["terminal_status"] == "failed"
    assert payload["spot_id"] == "abc"
    assert payload["failure_reason"] == "scrape_failed_after_max_retries"
