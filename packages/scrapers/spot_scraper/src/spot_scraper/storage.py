from datetime import datetime


SCHEMA_VERSION = 1
SOURCE_TYPE = "spot_report"


def build_spot_report_key(spot_id: str, scraped_at: datetime, run_id: str) -> str:
    scrape_date = scraped_at.strftime("%Y-%m-%d")
    return f"raw/spot_report/spot_id={spot_id}/scrape_date={scrape_date}/run_id={run_id}.json.gz"


def build_raw_spot_payload(
    *,
    spot_id: str,
    raw_payload: dict,
    run_id: str,
    scraped_at: str,
    discovery_run_id: str | None,
    sitemap_run_id: str | None,
    source_raw_key: str | None,
    requested_at: str | None = None,
) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "source_type": SOURCE_TYPE,
        "produced_at": scraped_at,
        "scraped_at": scraped_at,
        "spot_id": spot_id,
        "discovery_run_id": discovery_run_id,
        "sitemap_run_id": sitemap_run_id,
        "source_raw_key": source_raw_key,
        "requested_at": requested_at,
        "raw_payload": raw_payload,
    }
