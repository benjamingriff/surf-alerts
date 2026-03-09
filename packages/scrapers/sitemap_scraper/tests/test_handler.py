from datetime import datetime, timezone

from sitemap_scraper.storage import build_sitemap_key, build_sitemap_payload


def test_build_sitemap_key_uses_raw_partition_contract():
    scraped_at = datetime(2026, 3, 9, 6, 0, tzinfo=timezone.utc)

    key = build_sitemap_key(scraped_at=scraped_at, run_id="run-123")

    assert key == "raw/sitemap/scrape_date=2026-03-09/run_id=run-123.json.gz"


def test_build_sitemap_payload_wraps_raw_metadata():
    scraped_at = "2026-03-09T06:00:00+00:00"
    result = {
        "scraped_at": scraped_at,
        "spots": {
            "abc": {
                "spot_id": "abc",
                "link": "https://example.com/report",
                "forecast": "https://example.com/forecast",
            }
        },
    }

    payload = build_sitemap_payload(result=result, run_id="run-123")

    assert payload["schema_version"] == 1
    assert payload["run_id"] == "run-123"
    assert payload["source_type"] == "sitemap"
    assert payload["produced_at"] == scraped_at
    assert payload["scraped_at"] == scraped_at
    assert payload["spot_count"] == 1
    assert payload["spots"]["abc"]["spot_id"] == "abc"
