from datetime import datetime, timezone

from spot_scraper.storage import build_raw_spot_payload, build_spot_report_key


def test_build_spot_report_key_uses_target_contract():
    scraped_at = datetime(2026, 3, 9, 6, 5, tzinfo=timezone.utc)

    key = build_spot_report_key(spot_id="abc", scraped_at=scraped_at, run_id="run-123")

    assert key == (
        "raw/spot_report/spot_id=abc/scrape_date=2026-03-09/run_id=run-123.json.gz"
    )


def test_build_raw_spot_payload_wraps_discovery_metadata():
    raw_payload = {"spot": {"name": "Rest Bay"}}

    payload = build_raw_spot_payload(
        spot_id="abc",
        raw_payload=raw_payload,
        run_id="run-123",
        scraped_at="2026-03-09T06:05:00+00:00",
        discovery_run_id="discovery-1",
        sitemap_run_id="sitemap-1",
        source_raw_key="raw/sitemap/scrape_date=2026-03-09/run_id=sitemap-1.json.gz",
    )

    assert payload["schema_version"] == 1
    assert payload["run_id"] == "run-123"
    assert payload["source_type"] == "spot_report"
    assert payload["spot_id"] == "abc"
    assert payload["discovery_run_id"] == "discovery-1"
    assert payload["sitemap_run_id"] == "sitemap-1"
    assert payload["source_raw_key"].endswith("sitemap-1.json.gz")
    assert payload["raw_payload"] == raw_payload
