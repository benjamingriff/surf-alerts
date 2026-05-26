from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any


@dataclass(frozen=True)
class ForecastRows:
    ratings: list[dict[str, Any]]
    waves: list[dict[str, Any]]
    swells: list[dict[str, Any]]
    winds: list[dict[str, Any]]
    tides: list[dict[str, Any]]


def transform_forecast_envelope(envelope: dict[str, Any], *, source_raw_key: str) -> ForecastRows:
    """Transform one successful raw forecast envelope into v1 forecast fact rows."""

    payload = envelope.get("raw_payload", envelope)
    common = _common_fields(envelope, source_raw_key)

    return ForecastRows(
        ratings=_rating_rows(payload.get("rating"), common),
        waves=_wave_rows(payload.get("wave"), common),
        swells=_swell_rows(payload.get("wave"), common),
        winds=_wind_rows(payload.get("wind"), common),
        tides=_tide_rows(payload.get("tides"), common),
    )


def _common_fields(envelope: dict[str, Any], source_raw_key: str) -> dict[str, Any]:
    return {
        "forecast_run_id": envelope.get("forecast_run_id"),
        "spot_id": envelope.get("spot_id"),
        "spot_version_id": envelope.get("spot_version_id"),
        "scraped_at": envelope.get("scraped_at"),
        "scheduled_utc_time": envelope.get("scheduled_utc_time"),
        "utc_offset": envelope.get("utc_offset"),
        "timezone": envelope.get("timezone"),
        "source_raw_key": source_raw_key,
        "schema_version": envelope.get("schema_version", 1),
    }


def _ts(value: Any) -> str | None:
    if value is None:
        return None
    return datetime.fromtimestamp(value, tz=UTC).isoformat()


def _loc(prefix: str, loc: dict[str, Any] | None) -> dict[str, Any]:
    loc = loc or {}
    return {f"{prefix}_lon": loc.get("lon"), f"{prefix}_lat": loc.get("lat")}


def _rating_rows(payload: dict[str, Any] | None, common: dict[str, Any]) -> list[dict[str, Any]]:
    if not payload:
        return []
    associated = payload.get("associated", {})
    rows = []
    for item in payload.get("data", {}).get("rating", []):
        rating = item.get("rating") or {}
        rows.append(
            common
            | {
                "forecast_ts": _ts(item.get("timestamp")),
                "rating_key": rating.get("key"),
                "rating_value": rating.get("value"),
                "source_utc_offset": item.get("utcOffset"),
                "run_init_ts": _ts(associated.get("runInitializationTimestamp")),
            }
        )
    return rows


def _wave_rows(payload: dict[str, Any] | None, common: dict[str, Any]) -> list[dict[str, Any]]:
    if not payload:
        return []
    associated = payload.get("associated", {})
    rows = []
    for item in payload.get("data", {}).get("wave", []):
        surf = item.get("surf") or {}
        raw = surf.get("raw") or {}
        rows.append(
            common
            | {
                "forecast_ts": _ts(item.get("timestamp")),
                "surf_min": surf.get("min"),
                "surf_max": surf.get("max"),
                "surf_plus": surf.get("plus"),
                "surf_human_relation": surf.get("humanRelation"),
                "surf_raw_min": raw.get("min"),
                "surf_raw_max": raw.get("max"),
                "surf_optimal_score": surf.get("optimalScore"),
                "power": item.get("power"),
                "probability": item.get("probability"),
                "source_utc_offset": item.get("utcOffset", associated.get("utcOffset")),
                "run_init_ts": _ts(associated.get("runInitializationTimestamp")),
            }
            | _loc("location", associated.get("location"))
            | _loc("forecast_location", associated.get("forecastLocation"))
            | _loc("offshore_location", associated.get("offshoreLocation"))
        )
    return rows


def _swell_rows(payload: dict[str, Any] | None, common: dict[str, Any]) -> list[dict[str, Any]]:
    if not payload:
        return []
    rows = []
    for item in payload.get("data", {}).get("wave", []):
        for index, swell in enumerate(item.get("swells", [])):
            rows.append(
                common
                | {
                    "forecast_ts": _ts(item.get("timestamp")),
                    "swell_index": index,
                    "height": swell.get("height"),
                    "period": swell.get("period"),
                    "impact": swell.get("impact"),
                    "power": swell.get("power"),
                    "direction": swell.get("direction"),
                    "direction_min": swell.get("directionMin"),
                    "optimal_score": swell.get("optimalScore"),
                }
            )
    return rows


def _wind_rows(payload: dict[str, Any] | None, common: dict[str, Any]) -> list[dict[str, Any]]:
    if not payload:
        return []
    associated = payload.get("associated", {})
    rows = []
    for item in payload.get("data", {}).get("wind", []):
        rows.append(
            common
            | {
                "forecast_ts": _ts(item.get("timestamp")),
                "speed": item.get("speed"),
                "gust": item.get("gust"),
                "direction": item.get("direction"),
                "direction_type": item.get("directionType"),
                "optimal_score": item.get("optimalScore"),
                "source_utc_offset": item.get("utcOffset", associated.get("utcOffset")),
                "run_init_ts": _ts(associated.get("runInitializationTimestamp")),
            }
            | _loc("location", associated.get("location"))
        )
    return rows


def _tide_rows(payload: dict[str, Any] | None, common: dict[str, Any]) -> list[dict[str, Any]]:
    if not payload:
        return []
    associated = payload.get("associated", {})
    tide_location = associated.get("tideLocation") or {}
    rows = []
    for index, item in enumerate(payload.get("data", {}).get("tides", [])):
        rows.append(
            common
            | {
                "forecast_ts": _ts(item.get("timestamp")),
                "tide_index": index,
                "tide_type": item.get("type"),
                "height": item.get("height"),
                "source_utc_offset": item.get("utcOffset", associated.get("utcOffset")),
                "tide_location_name": tide_location.get("name"),
                "tide_location_lon": tide_location.get("lon"),
                "tide_location_lat": tide_location.get("lat"),
                "tide_location_min": tide_location.get("min"),
                "tide_location_max": tide_location.get("max"),
                "tide_location_mean": tide_location.get("mean"),
            }
        )
    return rows
