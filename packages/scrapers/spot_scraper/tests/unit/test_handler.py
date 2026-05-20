from spot_scraper.handler import process_spot_scrape_request
from spot_scraper.storage import build_spot_report_key


class FakeWriter:
    def __init__(self, calls):
        self.calls = calls

    def put_json(self, *, bucket, key, body):
        self.calls.append({"bucket": bucket, "key": key, "body": body})
        return f"s3://{bucket}/{key}"


def test_build_spot_report_key_is_deterministic_v1_shape():
    assert (
        build_spot_report_key(
            scrape_date="2026-05-01",
            discovery_run_id="run-123",
            spot_id="spot-a",
        )
        == "raw/spot_report/scrape_date=2026-05-01/discovery_run_id=run-123/spot_id=spot-a.json.gz"
    )


def test_process_request_writes_raw_payload_to_expected_s3_shape(monkeypatch):
    writes = []
    completions = []
    monkeypatch.setattr("spot_scraper.handler._exists", lambda bucket, key: False)
    monkeypatch.setattr(
        "spot_scraper.handler._fetch_spot_report",
        lambda spot_id: {"spot": {"name": f"Spot {spot_id}"}},
    )
    monkeypatch.setattr("spot_scraper.handler._s3_writer", lambda: FakeWriter(writes))
    monkeypatch.setattr("spot_scraper.handler._send_completion", completions.append)
    monkeypatch.setattr("spot_scraper.handler._utc_now_iso", lambda: "2026-05-01T06:02:10Z")

    result = process_spot_scrape_request(
        {
            "schema_version": 1,
            "message_type": "spot_scrape_requested",
            "discovery_run_id": "run-123",
            "scrape_date": "2026-05-01",
            "spot_id": "spot-a",
            "sitemap_raw_key": "raw/sitemap/scrape_date=2026-05-01/discovery_run_id=run-123.json.gz",
            "requested_at": "2026-05-01T06:01:00Z",
        },
        bucket="data-bucket",
    )

    assert writes == [
        {
            "bucket": "data-bucket",
            "key": "raw/spot_report/scrape_date=2026-05-01/discovery_run_id=run-123/spot_id=spot-a.json.gz",
            "body": {
                "schema_version": 1,
                "run_id": "run-123",
                "source_type": "spot_report",
                "produced_at": "2026-05-01T06:02:10Z",
                "scraped_at": "2026-05-01T06:02:10Z",
                "spot_id": "spot-a",
                "discovery_run_id": "run-123",
                "sitemap_run_id": None,
                "source_raw_key": "raw/sitemap/scrape_date=2026-05-01/discovery_run_id=run-123.json.gz",
                "requested_at": "2026-05-01T06:01:00Z",
                "raw_payload": {"spot": {"name": "Spot spot-a"}},
            },
        }
    ]
    assert result == completions[0]
    assert result["terminal_status"] == "success"
    assert result["raw_bucket"] == "data-bucket"
    assert result["raw_key"] == writes[0]["key"]


def test_existing_raw_object_skips_fetch_and_write_but_sends_success(monkeypatch):
    completions = []
    monkeypatch.setattr("spot_scraper.handler._exists", lambda bucket, key: True)
    monkeypatch.setattr(
        "spot_scraper.handler._fetch_spot_report",
        lambda spot_id: (_ for _ in ()).throw(AssertionError("should not fetch")),
    )
    monkeypatch.setattr(
        "spot_scraper.handler._s3_writer",
        lambda: (_ for _ in ()).throw(AssertionError("should not write")),
    )
    monkeypatch.setattr("spot_scraper.handler._send_completion", completions.append)
    monkeypatch.setattr("spot_scraper.handler._utc_now_iso", lambda: "2026-05-01T06:02:10Z")

    result = process_spot_scrape_request(
        {"discovery_run_id": "run-123", "scrape_date": "2026-05-01", "spot_id": "spot-a"},
        bucket="data-bucket",
    )

    assert result["terminal_status"] == "success"
    assert (
        result["raw_key"]
        == "raw/spot_report/scrape_date=2026-05-01/discovery_run_id=run-123/spot_id=spot-a.json.gz"
    )
    assert completions == [result]


def test_fetch_failure_sends_failure_completion_without_raising(monkeypatch):
    completions = []
    monkeypatch.setattr("spot_scraper.handler._exists", lambda bucket, key: False)
    monkeypatch.setattr(
        "spot_scraper.handler._fetch_spot_report",
        lambda spot_id: (_ for _ in ()).throw(RuntimeError("HTTP 403")),
    )
    monkeypatch.setattr("spot_scraper.handler._send_completion", completions.append)
    monkeypatch.setattr("spot_scraper.handler._utc_now_iso", lambda: "2026-05-01T06:02:10Z")

    result = process_spot_scrape_request(
        {"discovery_run_id": "run-123", "scrape_date": "2026-05-01", "spot_id": "spot-a"},
        bucket="data-bucket",
    )

    assert result["terminal_status"] == "failed"
    assert result["raw_bucket"] is None
    assert result["raw_key"] is None
    assert result["failure_reason"] == "HTTP 403"
    assert completions == [result]
