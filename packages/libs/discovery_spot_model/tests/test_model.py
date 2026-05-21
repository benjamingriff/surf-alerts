from discovery_spot_model import (
    build_removed_tombstone_row,
    canonicalize_spot_report,
    compute_spot_checksum,
    deterministic_discovery_run_id,
)


def _payload(name="A"):
    return {
        "raw_payload": {
            "spot": {
                "spot_id": "spot-a",
                "name": name,
                "location": {"lon": 2, "lat": 1},
                "timezone": "Europe/London",
                "utcOffset": 0,
                "abbrTimezone": "GMT",
                "href": "https://example.com/spot-a",
            }
        }
    }


def test_deterministic_run_id_is_day_scoped():
    assert deterministic_discovery_run_id("2026-05-01") == deterministic_discovery_run_id(
        "2026-05-01"
    )
    assert deterministic_discovery_run_id("2026-05-01") != deterministic_discovery_run_id(
        "2026-05-02"
    )


def test_canonical_checksum_ignores_key_order():
    a = canonicalize_spot_report(_payload(), "spot-a")
    b = canonicalize_spot_report(_payload(), "spot-a")
    assert a["lat"] == 1
    assert compute_spot_checksum(a) == compute_spot_checksum(b)


def test_removed_tombstone_carries_descriptive_fields():
    row = build_removed_tombstone_row(
        current_row={"spot_id": "s1", "name": "Old", "content_checksum": "abc"},
        discovery_run_id="run",
        source_raw_key="raw/sitemap/x",
        valid_from="2026-05-01T00:00:00Z",
    )
    assert row["event_type"] == "removed"
    assert row["is_current"] is True
    assert row["name"] == "Old"
    assert row["source_type"] == "sitemap"
