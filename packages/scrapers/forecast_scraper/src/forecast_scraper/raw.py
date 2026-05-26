from datetime import UTC, datetime
from urllib.parse import quote

RAW_SCHEMA_VERSION = 1
SOURCE_TYPE = "forecast_report"


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def build_raw_key(
    *, scrape_date: str, utc_offset: int | str, forecast_run_id: str, spot_id: str
) -> str:
    safe_run_id = quote(forecast_run_id, safe="=-#")
    safe_spot_id = quote(spot_id, safe="")
    return (
        f"raw/forecast/scrape_date={scrape_date}/utc_offset={utc_offset}/"
        f"forecast_run_id={safe_run_id}/spot_id={safe_spot_id}.json.gz"
    )


def build_raw_envelope(*, request: dict, payload: dict, scraped_at: str) -> dict:
    return {
        "schema_version": RAW_SCHEMA_VERSION,
        "source_type": SOURCE_TYPE,
        "forecast_run_id": request["forecast_run_id"],
        "spot_id": request["spot_id"],
        "spot_version_id": request.get("spot_version_id"),
        "spot_name": request.get("spot_name"),
        "scheduled_utc_time": request["scheduled_utc_time"],
        "scraped_at": scraped_at,
        "utc_offset": request.get("utc_offset"),
        "timezone": request.get("timezone"),
        "latitude": request.get("latitude"),
        "longitude": request.get("longitude"),
        "raw_payload": payload,
    }
