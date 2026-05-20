import hashlib
import json

import pytest

from discovery_spot_model import (
    build_added_spot_version_row,
    build_removed_tombstone_row,
    canonicalize_spot_report,
    compute_spot_checksum,
    deterministic_discovery_run_id,
    deterministic_spot_version_id,
)


def test_deterministic_run_id_is_day_scoped_sha256():
    expected = hashlib.sha256("discovery:2026-05-01".encode()).hexdigest()
    assert deterministic_discovery_run_id("2026-05-01") == expected
    assert deterministic_discovery_run_id("2026-05-01") != deterministic_discovery_run_id(
        "2026-05-02"
    )


def test_deterministic_added_version_id_uses_spot_id_and_checksum():
    expected = hashlib.sha256("spot-a:checksum-1".encode()).hexdigest()
    assert deterministic_spot_version_id("spot-a", "checksum-1") == expected


def test_deterministic_removed_version_id_requires_discovery_run_id():
    with pytest.raises(ValueError, match="discovery_run_id is required"):
        deterministic_spot_version_id("spot-a", "", removed=True)


def test_deterministic_removed_version_id_uses_spot_run_and_removed_marker():
    expected = hashlib.sha256("spot-a:removed:run-1".encode()).hexdigest()
    assert (
        deterministic_spot_version_id("spot-a", "ignored", removed=True, discovery_run_id="run-1")
        == expected
    )


def test_canonicalize_spot_report_flattens_representative_surfline_payload():
    raw = {
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
                "breadCrumbs": [{"name": "Ireland", "href": "/ireland"}],
                "cameras": [{"id": "cam-1", "title": "Main"}],
                "abilityLevels": ["INTERMEDIATE", "BEGINNER"],
                "boardTypes": [{"name": "Shortboard"}],
                "travelDetails": {"best": {"season": "winter"}},
            }
        }
    }

    canonical = canonicalize_spot_report(raw, "spot-a")

    assert canonical == {
        "spot_id": "spot-a",
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
        "breadcrumbs": [{"href": "/ireland", "name": "Ireland"}],
        "cameras": [{"id": "cam-1", "title": "Main"}],
        "ability_levels": ["BEGINNER", "INTERMEDIATE"],
        "board_types": [{"name": "Shortboard"}],
        "travel_details": {"best": {"season": "winter"}},
    }


def test_canonicalize_spot_report_handles_missing_optional_fields():
    canonical = canonicalize_spot_report({"raw_payload": {"spot": {"name": "Minimal"}}}, "spot-min")

    assert canonical["spot_id"] == "spot-min"
    assert canonical["name"] == "Minimal"
    assert canonical["lat"] is None
    assert canonical["lon"] is None
    assert canonical["breadcrumbs"] == []
    assert canonical["cameras"] == []
    assert canonical["ability_levels"] == []
    assert canonical["board_types"] == []
    assert canonical["travel_details"] == {}


def test_canonicalize_spot_report_handles_unexpected_raw_payload_type_as_empty_spot():
    canonical = canonicalize_spot_report({"raw_payload": ["not", "a", "dict"]}, "spot-a")

    assert canonical["spot_id"] == "spot-a"
    assert canonical["name"] is None
    assert canonical["breadcrumbs"] == []


def test_compute_checksum_is_stable_for_nested_key_and_array_order():
    a = {
        "spot_id": "spot-a",
        "board_types": [{"b": 2, "a": 1}, {"name": "Fish"}],
        "travel_details": {"z": 1, "a": 2},
    }
    b = {
        "travel_details": {"a": 2, "z": 1},
        "board_types": [{"name": "Fish"}, {"a": 1, "b": 2}],
        "spot_id": "spot-a",
    }

    assert compute_spot_checksum(a) == compute_spot_checksum(b)
    assert (
        compute_spot_checksum(a)
        == hashlib.sha256(
            json.dumps(
                {
                    "board_types": [{"a": 1, "b": 2}, {"name": "Fish"}],
                    "spot_id": "spot-a",
                    "travel_details": {"a": 2, "z": 1},
                },
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
    )


def test_build_added_spot_version_row_includes_scd2_and_source_fields():
    canonical = canonicalize_spot_report({"raw_payload": {"spot": {"name": "A"}}}, "spot-a")

    row = build_added_spot_version_row(
        canonical_spot=canonical,
        discovery_run_id="run-1",
        source_raw_key="raw/spot_report/x.json.gz",
        valid_from="2026-05-01T06:10:00Z",
    )

    checksum = compute_spot_checksum(canonical)
    assert row["spot_version_id"] == deterministic_spot_version_id("spot-a", checksum)
    assert row["event_type"] == "added"
    assert row["is_current"] is True
    assert row["valid_to"] is None
    assert row["content_checksum"] == checksum
    assert row["source_run_id"] == "run-1"
    assert row["source_raw_key"] == "raw/spot_report/x.json.gz"
    assert row["source_type"] == "spot_report"
    assert row["schema_version"] == 1


def test_build_added_spot_version_row_requires_spot_id():
    with pytest.raises(KeyError):
        build_added_spot_version_row(
            canonical_spot={"name": "No id"},
            discovery_run_id="run-1",
            source_raw_key="raw/spot_report/x.json.gz",
            valid_from="2026-05-01T06:10:00Z",
        )


def test_build_removed_tombstone_row_carries_forward_descriptive_fields():
    current = {
        "spot_id": "spot-a",
        "content_checksum": "old-checksum",
        "name": "Old Spot",
        "lat": 1.0,
        "lon": 2.0,
        "timezone": "Europe/London",
        "breadcrumbs": [{"name": "UK"}],
        "travel_details": {"access": "walk"},
    }

    row = build_removed_tombstone_row(
        current_row=current,
        discovery_run_id="run-1",
        source_raw_key="raw/sitemap/x.json.gz",
        valid_from="2026-05-01T06:10:00Z",
    )

    assert row["spot_version_id"] == deterministic_spot_version_id(
        "spot-a", "", removed=True, discovery_run_id="run-1"
    )
    assert row["event_type"] == "removed"
    assert row["is_current"] is True
    assert row["valid_to"] is None
    assert row["name"] == "Old Spot"
    assert row["content_checksum"] == "old-checksum"
    assert row["breadcrumbs"] == [{"name": "UK"}]
    assert row["source_type"] == "sitemap"


def test_build_removed_tombstone_row_requires_spot_id():
    with pytest.raises(ValueError, match="spot_id is required"):
        build_removed_tombstone_row(
            current_row={"name": "No id"},
            discovery_run_id="run-1",
            source_raw_key="raw/sitemap/x.json.gz",
            valid_from="2026-05-01T06:10:00Z",
        )
