from discovery_spot_model import (
    build_added_spot_version_row,
    build_removed_tombstone_row,
    canonicalize_spot_report,
    compute_spot_checksum,
    deterministic_spot_version_id,
)


def test_raw_spot_report_envelope_to_added_scd2_row_success_path():
    raw_envelope = {
        "schema_version": 1,
        "source_type": "spot_report",
        "spot_id": "spot-a",
        "discovery_run_id": "run-1",
        "raw_payload": {
            "spot": {
                "name": "Bundoran",
                "location": {"lat": 54.477, "lon": -8.28},
                "timezone": "Europe/Dublin",
                "utcOffset": 0,
                "abbrTimezone": "GMT",
                "subregion": {"_id": "sub-1", "name": "Donegal"},
                "sitemapLink": "/surf-report/bundoran/spot-a",
                "forecastLink": "/surf-forecasts/bundoran/spot-a",
                "abilityLevels": ["INTERMEDIATE", "BEGINNER"],
                "boardTypes": [{"name": "Shortboard"}],
                "travelDetails": {"best": {"season": "winter"}},
            }
        },
    }

    canonical = canonicalize_spot_report(raw_envelope, "spot-a")
    row = build_added_spot_version_row(
        canonical_spot=canonical,
        discovery_run_id="run-1",
        source_raw_key="raw/spot_report/scrape_date=2026-05-01/discovery_run_id=run-1/spot_id=spot-a.json.gz",
        valid_from="2026-05-01T06:10:00Z",
    )

    checksum = compute_spot_checksum(canonical)
    assert row["spot_version_id"] == deterministic_spot_version_id("spot-a", checksum)
    assert row["spot_id"] == "spot-a"
    assert row["event_type"] == "added"
    assert row["is_current"] is True
    assert row["content_checksum"] == checksum
    assert row["source_type"] == "spot_report"
    assert row["name"] == "Bundoran"
    assert row["ability_levels"] == ["BEGINNER", "INTERMEDIATE"]


def test_current_active_row_to_removed_tombstone_success_path():
    current_active_row = {
        "spot_version_id": "old-version",
        "spot_id": "spot-a",
        "event_type": "added",
        "is_current": True,
        "content_checksum": "old-checksum",
        "name": "Bundoran",
        "lat": 54.477,
        "lon": -8.28,
        "timezone": "Europe/Dublin",
        "utc_offset": 0,
        "abbr_timezone": "GMT",
        "subregion_id": "sub-1",
        "subregion_name": "Donegal",
        "sitemap_link": "/surf-report/bundoran/spot-a",
        "forecast_link": "/surf-forecasts/bundoran/spot-a",
        "breadcrumbs": [{"name": "Ireland"}],
        "cameras": [],
        "ability_levels": ["BEGINNER", "INTERMEDIATE"],
        "board_types": [{"name": "Shortboard"}],
        "travel_details": {"best": {"season": "winter"}},
    }

    tombstone = build_removed_tombstone_row(
        current_row=current_active_row,
        discovery_run_id="run-removed",
        source_raw_key="raw/sitemap/scrape_date=2026-05-01/discovery_run_id=run-removed.json.gz",
        valid_from="2026-05-01T06:10:00Z",
    )

    assert tombstone["spot_version_id"] == deterministic_spot_version_id(
        "spot-a", "", removed=True, discovery_run_id="run-removed"
    )
    assert tombstone["event_type"] == "removed"
    assert tombstone["is_current"] is True
    assert tombstone["source_type"] == "sitemap"
    assert tombstone["content_checksum"] == "old-checksum"
    assert tombstone["name"] == "Bundoran"
    assert tombstone["travel_details"] == {"best": {"season": "winter"}}


def test_failed_scrape_payload_is_not_convertible_to_added_business_row():
    failed_completion_payload = {
        "schema_version": 1,
        "message_type": "spot_scrape_complete",
        "terminal_status": "failed",
        "discovery_run_id": "run-1",
        "spot_id": "spot-a",
        "raw_bucket": None,
        "raw_key": None,
        "failure_reason": "HTTP 403",
    }

    canonical = canonicalize_spot_report(failed_completion_payload, "spot-a")

    # The model can tolerate unexpected payloads for robustness, but the batch processor should
    # only pass successful raw spot report envelopes. A failure completion has no Surfline spot data.
    assert canonical["name"] is None
    assert canonical["lat"] is None
    assert canonical["lon"] is None


def test_checksum_changes_when_canonical_business_content_changes():
    raw = {"raw_payload": {"spot": {"name": "A", "location": {"lat": 1, "lon": 2}}}}
    changed = {"raw_payload": {"spot": {"name": "B", "location": {"lat": 1, "lon": 2}}}}

    assert compute_spot_checksum(canonicalize_spot_report(raw, "spot-a")) != compute_spot_checksum(
        canonicalize_spot_report(changed, "spot-a")
    )
