import hashlib
import json
from copy import deepcopy
from typing import Any

SCHEMA_VERSION = 1
JSON_FIELDS = {"breadcrumbs", "travel_details"}
REQUIRED_SPOT_FIELDS = (
    "spot_id",
    "name",
    "lat",
    "lon",
    "timezone",
    "utc_offset",
    "abbr_timezone",
    "href",
)


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def deterministic_discovery_run_id(scrape_date: str) -> str:
    return _sha256(f"discovery:{scrape_date}")


def deterministic_spot_version_id(
    spot_id: str,
    content_checksum: str,
    *,
    removed: bool = False,
    discovery_run_id: str | None = None,
) -> str:
    if not spot_id:
        raise ValueError("spot_id is required for spot version ids")
    if removed:
        if not discovery_run_id:
            raise ValueError("discovery_run_id is required for removed version ids")
        return _sha256(f"{spot_id}:removed:{discovery_run_id}")
    return _sha256(f"{spot_id}:{content_checksum}")


def _first_mapping(payload: dict[str, Any]) -> dict[str, Any]:
    raw = payload.get("raw_payload", payload)
    if isinstance(raw, dict):
        return (
            raw.get("spot")
            or raw.get("data", {}).get("spot")
            or raw.get("associated", {}).get("spot")
            or raw
        )
    return {}


def _norm(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, dict):
        return {k: _norm(value[k]) for k in sorted(value)}
    if isinstance(value, list):
        items = [_norm(v) for v in value]
        try:
            return sorted(items, key=lambda item: json.dumps(item, sort_keys=True))
        except TypeError:
            return items
    return value


def canonicalize_spot_report(raw_payload: dict[str, Any], spot_id: str) -> dict[str, Any]:
    spot = _first_mapping(raw_payload)
    location = spot.get("location") or {}
    canonical = {
        "spot_id": spot.get("spot_id") or spot.get("_id"),
        "name": spot.get("name"),
        "lat": location.get("lat") if location.get("lat") is not None else spot.get("lat"),
        "lon": location.get("lon") if location.get("lon") is not None else spot.get("lon"),
        "timezone": spot.get("timezone"),
        "utc_offset": spot.get("utc_offset") if spot.get("utc_offset") is not None else spot.get("utcOffset"),
        "abbr_timezone": spot.get("abbr_timezone") or spot.get("abbrTimezone"),
        "href": spot.get("href") or spot.get("sitemapLink") or spot.get("sitemap_link"),
        "breadcrumbs": _norm(spot.get("breadCrumbs") or spot.get("breadcrumbs") or []),
        "subregion": _norm(spot.get("subregion") or {}),
        "travel_details": _norm(spot.get("travelDetails") or spot.get("travel_details") or {}),
    }
    missing = [field for field in REQUIRED_SPOT_FIELDS if canonical.get(field) is None]
    if missing:
        raise ValueError(f"Missing required spot fields for {spot_id}: {', '.join(missing)}")
    return canonical


def compute_spot_checksum(canonical_spot: dict[str, Any]) -> str:
    return _sha256(json.dumps(_norm(canonical_spot), sort_keys=True, separators=(",", ":")))


def build_added_spot_version_row(
    *,
    canonical_spot: dict[str, Any],
    discovery_run_id: str,
    source_raw_key: str,
    valid_from: str,
) -> dict[str, Any]:
    checksum = compute_spot_checksum(canonical_spot)
    row = deepcopy(canonical_spot)
    row.update(
        {
            "spot_version_id": deterministic_spot_version_id(canonical_spot["spot_id"], checksum),
            "event_type": "added",
            "is_current": True,
            "valid_from": valid_from,
            "valid_to": None,
            "content_checksum": checksum,
            "source_run_id": discovery_run_id,
            "source_raw_key": source_raw_key,
            "source_type": "spot_report",
            "schema_version": SCHEMA_VERSION,
        }
    )
    return row


def build_removed_tombstone_row(
    *,
    current_row: dict[str, Any],
    discovery_run_id: str,
    source_raw_key: str,
    valid_from: str,
) -> dict[str, Any]:
    row = {
        k: current_row.get(k)
        for k in [
            "spot_id",
            "content_checksum",
            "name",
            "lat",
            "lon",
            "timezone",
            "utc_offset",
            "abbr_timezone",
            "href",
            *JSON_FIELDS,
            "subregion",
        ]
    }
    row.update(
        {
            "spot_version_id": deterministic_spot_version_id(
                row["spot_id"], "", removed=True, discovery_run_id=discovery_run_id
            ),
            "event_type": "removed",
            "is_current": True,
            "valid_from": valid_from,
            "valid_to": None,
            "source_run_id": discovery_run_id,
            "source_raw_key": source_raw_key,
            "source_type": "sitemap",
            "schema_version": SCHEMA_VERSION,
        }
    )
    return row
