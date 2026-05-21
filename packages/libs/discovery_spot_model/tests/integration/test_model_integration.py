import json
from pathlib import Path

import pytest

from discovery_spot_model import (
    build_added_spot_version_row,
    build_removed_tombstone_row,
    canonicalize_spot_report,
    compute_spot_checksum,
    deterministic_spot_version_id,
)


EXAMPLE_SPOT_PATH = (
    Path(__file__).resolve().parents[5] / "data" / "spot" / "2026-05-21T11-33-01" / "data.json"
)


def test_current_spot_scraper_payload_to_added_scd2_row_success_path():
    raw_payload = json.loads(EXAMPLE_SPOT_PATH.read_text())
    spot_id = raw_payload["spot"]["spot_id"]

    canonical = canonicalize_spot_report(raw_payload, spot_id)
    row = build_added_spot_version_row(
        canonical_spot=canonical,
        discovery_run_id="run-1",
        source_raw_key=f"raw/spot_report/scrape_date=2026-05-21/discovery_run_id=run-1/spot_id={spot_id}.json.gz",
        valid_from="2026-05-21T10:10:00Z",
    )

    checksum = compute_spot_checksum(canonical)
    assert row["spot_version_id"] == deterministic_spot_version_id(spot_id, checksum)
    assert row["spot_id"] == spot_id
    assert row["event_type"] == "added"
    assert row["is_current"] is True
    assert row["content_checksum"] == checksum
    assert row["source_type"] == "spot_report"
    assert row["name"] == "Rest Bay"
    assert row["lat"] == 51.488
    assert row["lon"] == -3.728
    assert row["timezone"] == "Europe/London"
    assert row["utc_offset"] == 1
    assert row["abbr_timezone"] == "BST"
    assert row["href"] == "https://www.surfline.com/surf-report/rest-bay/584204204e65fad6a77090d2"
    assert "cameras" not in row
    assert "ability_levels" not in row
    assert "board_types" not in row


@pytest.mark.parametrize("field", ["spot_id", "name", "lat", "lon", "timezone", "utc_offset", "abbr_timezone", "href"])
def test_current_spot_scraper_payload_requires_core_fields(field):
    raw_payload = json.loads(EXAMPLE_SPOT_PATH.read_text())
    spot_id = raw_payload["spot"]["spot_id"]
    raw_payload["spot"].pop(field)

    with pytest.raises(ValueError, match="Missing required spot fields"):
        canonicalize_spot_report(raw_payload, spot_id)


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
        "href": "/surf-report/bundoran/spot-a",
        "breadcrumbs": [{"name": "Ireland"}],
        "subregion": {"_id": "sub-1", "name": "Donegal"},
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
    assert tombstone["href"] == "/surf-report/bundoran/spot-a"
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

    with pytest.raises(ValueError, match="Missing required spot fields"):
        canonicalize_spot_report(failed_completion_payload, "spot-a")


def test_checksum_changes_when_canonical_business_content_changes():
    raw = json.loads(EXAMPLE_SPOT_PATH.read_text())
    changed = json.loads(EXAMPLE_SPOT_PATH.read_text())
    changed["spot"]["name"] = "Rest Bay Changed"

    assert compute_spot_checksum(canonicalize_spot_report(raw, raw["spot"]["spot_id"])) != compute_spot_checksum(
        canonicalize_spot_report(changed, changed["spot"]["spot_id"])
    )
