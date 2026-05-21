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


REST_BAY_SPOT = {
    "spot_id": "584204204e65fad6a77090d2",
    "name": "Rest Bay",
    "lat": 51.488,
    "lon": -3.728,
    "timezone": "Europe/London",
    "utc_offset": 1,
    "abbr_timezone": "BST",
    "href": "https://www.surfline.com/surf-report/rest-bay/584204204e65fad6a77090d2",
    "breadcrumbs": [
        {"name": "United Kingdom", "href": "https://www.surfline.com/uk"},
        {"name": "Wales", "href": "https://www.surfline.com/wales"},
    ],
    "subregion": {
        "_id": "612801eb3f4e20988f77c71f",
        "forecastStatus": "active",
        "name": "Severn Estuary",
    },
    "cameras": [{"id": "cam-1"}],
    "ability_levels": ["BEGINNER"],
    "board_types": ["SHORTBOARD"],
    "travel_details": {"best_season": ["Autumn", "Winter"], "spot_rating": 5},
}


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


def test_canonicalize_spot_report_flattens_current_spot_scraper_payload_shape():
    canonical = canonicalize_spot_report({"spot": REST_BAY_SPOT}, REST_BAY_SPOT["spot_id"])

    assert canonical == {
        "spot_id": "584204204e65fad6a77090d2",
        "name": "Rest Bay",
        "lat": 51.488,
        "lon": -3.728,
        "timezone": "Europe/London",
        "utc_offset": 1,
        "abbr_timezone": "BST",
        "href": "https://www.surfline.com/surf-report/rest-bay/584204204e65fad6a77090d2",
        "breadcrumbs": [
            {"href": "https://www.surfline.com/uk", "name": "United Kingdom"},
            {"href": "https://www.surfline.com/wales", "name": "Wales"},
        ],
        "subregion": {
            "_id": "612801eb3f4e20988f77c71f",
            "forecastStatus": "active",
            "name": "Severn Estuary",
        },
        "travel_details": {"best_season": ["Autumn", "Winter"], "spot_rating": 5},
    }
    assert "cameras" not in canonical
    assert "ability_levels" not in canonical
    assert "board_types" not in canonical


def test_canonicalize_spot_report_uses_associated_metadata_from_raw_scraper_envelope():
    raw = {
        "raw_payload": {
            "associated": {
                "href": "https://www.surfline.com/surf-report/south-ocean-beach/spot-a",
                "utcOffset": -7,
                "abbrTimezone": "PDT",
                "timezone": "America/Los_Angeles",
            },
            "spot": {
                "_id": "spot-a",
                "name": "South Ocean Beach",
                "breadcrumb": [{"name": "United States", "href": "/united-states"}],
                "lat": 37.741668,
                "lon": -122.51038,
                "subregion": {"_id": "sub-1", "name": "San Francisco"},
                "travelDetails": {"access": "Public parking"},
            },
        }
    }

    canonical = canonicalize_spot_report(raw, "spot-a")

    assert canonical["spot_id"] == "spot-a"
    assert canonical["name"] == "South Ocean Beach"
    assert canonical["timezone"] == "America/Los_Angeles"
    assert canonical["utc_offset"] == -7
    assert canonical["abbr_timezone"] == "PDT"
    assert canonical["href"] == "https://www.surfline.com/surf-report/south-ocean-beach/spot-a"
    assert canonical["breadcrumbs"] == [{"href": "/united-states", "name": "United States"}]


def test_canonicalize_spot_report_still_accepts_raw_surfline_camel_case_fields():
    raw = {
        "raw_payload": {
            "spot": {
                "_id": "spot-a",
                "name": "Bundoran",
                "location": {"lat": 54.477, "lon": -8.28},
                "timezone": "Europe/Dublin",
                "utcOffset": 0,
                "abbrTimezone": "GMT",
                "href": "/surf-report/bundoran/spot-a",
                "breadCrumbs": [{"name": "Ireland", "href": "/ireland"}],
                "subregion": {"_id": "sub-1", "name": "Donegal"},
                "travelDetails": {"best": {"season": "winter"}},
            }
        }
    }

    canonical = canonicalize_spot_report(raw, "spot-a")

    assert canonical["spot_id"] == "spot-a"
    assert canonical["utc_offset"] == 0
    assert canonical["abbr_timezone"] == "GMT"
    assert canonical["href"] == "/surf-report/bundoran/spot-a"
    assert canonical["breadcrumbs"] == [{"href": "/ireland", "name": "Ireland"}]


def test_canonicalize_spot_report_raises_when_required_fields_are_missing():
    with pytest.raises(ValueError, match="Missing required spot fields"):
        canonicalize_spot_report({"raw_payload": {"spot": {"name": "Minimal"}}}, "spot-min")


def test_canonicalize_spot_report_handles_unexpected_raw_payload_type_as_missing_required_fields():
    with pytest.raises(ValueError, match="Missing required spot fields"):
        canonicalize_spot_report({"raw_payload": ["not", "a", "dict"]}, "spot-a")


def test_compute_checksum_is_stable_for_nested_key_and_array_order():
    a = {
        "spot_id": "spot-a",
        "breadcrumbs": [{"b": 2, "a": 1}, {"name": "Wales"}],
        "travel_details": {"z": 1, "a": 2},
    }
    b = {
        "travel_details": {"a": 2, "z": 1},
        "breadcrumbs": [{"name": "Wales"}, {"a": 1, "b": 2}],
        "spot_id": "spot-a",
    }

    assert compute_spot_checksum(a) == compute_spot_checksum(b)
    assert (
        compute_spot_checksum(a)
        == hashlib.sha256(
            json.dumps(
                {
                    "breadcrumbs": [{"a": 1, "b": 2}, {"name": "Wales"}],
                    "spot_id": "spot-a",
                    "travel_details": {"a": 2, "z": 1},
                },
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
    )


def test_build_added_spot_version_row_includes_scd2_and_source_fields():
    canonical = canonicalize_spot_report({"spot": REST_BAY_SPOT}, REST_BAY_SPOT["spot_id"])

    row = build_added_spot_version_row(
        canonical_spot=canonical,
        discovery_run_id="run-1",
        source_raw_key="raw/spot_report/x.json.gz",
        valid_from="2026-05-01T06:10:00Z",
    )

    checksum = compute_spot_checksum(canonical)
    assert row["spot_version_id"] == deterministic_spot_version_id(
        REST_BAY_SPOT["spot_id"], checksum
    )
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
        "utc_offset": 0,
        "abbr_timezone": "GMT",
        "href": "/surf-report/old/spot-a",
        "breadcrumbs": [{"name": "UK"}],
        "subregion": {"_id": "sub-1", "name": "Region"},
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
    assert row["href"] == "/surf-report/old/spot-a"
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
