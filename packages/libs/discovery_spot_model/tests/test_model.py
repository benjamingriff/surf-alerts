from discovery_spot_model import (
    canonicalize_spot_report,
    compute_spot_checksum,
    deterministic_discovery_run_id,
    build_removed_tombstone_row,
)


def test_deterministic_run_id_is_day_scoped():
    assert deterministic_discovery_run_id("2026-05-01") == deterministic_discovery_run_id(
        "2026-05-01"
    )
    assert deterministic_discovery_run_id("2026-05-01") != deterministic_discovery_run_id(
        "2026-05-02"
    )


def test_canonical_checksum_ignores_key_order():
    payload = {
        "raw_payload": {
            "spot": {
                "name": "A",
                "location": {"lon": 2, "lat": 1},
                "boardTypes": [{"b": 2, "a": 1}],
            }
        }
    }
    a = canonicalize_spot_report(payload, "spot-a")
    b = canonicalize_spot_report(payload, "spot-a")
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
