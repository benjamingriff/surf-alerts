import gzip
import json

from spot_scraper.handler import lambda_handler


def test_spot_scraper_writes_raw_report_and_completion_marker(s3, monkeypatch, lambda_context):
    bucket = "dataeng-squeegee-test-bucket"
    monkeypatch.setenv("DATA_BUCKET", bucket)
    monkeypatch.setattr(
        "spot_scraper.handler._fetch_spot_report",
        lambda spot_id: {
            "spot": {"name": f"Spot {spot_id}", "lat": 51.0, "lon": -3.0},
            "associated": {"timezone": "Europe/London", "utcOffset": 0, "abbrTimezone": "GMT"},
        },
    )

    response = lambda_handler(
        {
            "Records": [
                {
                    "body": json.dumps(
                        {
                            "spot_id": "abc",
                            "discovery_run_id": "run-1",
                            "sitemap_run_id": "run-1",
                            "source_raw_key": "raw/sitemap/scrape_date=2026-03-09/run_id=run-1.json.gz",
                            "requested_at": "2026-03-09T06:00:00Z",
                        }
                    )
                }
            ]
        },
        lambda_context,
    )

    assert response["statusCode"] == 200

    raw_objects = s3.list_objects_v2(Bucket=bucket, Prefix="raw/spot_report/spot_id=abc/")["Contents"]
    completion_objects = s3.list_objects_v2(
        Bucket=bucket,
        Prefix="control/completions/discovery_spot_scrapes/date=",
    )["Contents"]
    assert len(raw_objects) == 1
    assert len(completion_objects) == 1

    completion_payload = json.loads(
        gzip.decompress(
            s3.get_object(Bucket=bucket, Key=completion_objects[0]["Key"])["Body"].read()
        ).decode("utf-8")
    )
    assert completion_payload["discovery_run_id"] == "run-1"
    assert completion_payload["spot_id"] == "abc"
    assert completion_payload["terminal_status"] == "success"
