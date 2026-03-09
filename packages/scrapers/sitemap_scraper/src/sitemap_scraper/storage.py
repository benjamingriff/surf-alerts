from datetime import datetime


SCHEMA_VERSION = 1
SOURCE_TYPE = "sitemap"


def build_sitemap_key(scraped_at: datetime, run_id: str) -> str:
    scrape_date = scraped_at.strftime("%Y-%m-%d")
    return f"raw/sitemap/scrape_date={scrape_date}/run_id={run_id}.json.gz"


def build_sitemap_payload(result: dict, run_id: str) -> dict:
    scraped_at = result["scraped_at"]
    return {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "source_type": SOURCE_TYPE,
        "produced_at": scraped_at,
        "scraped_at": scraped_at,
        "spot_count": len(result["spots"]),
        "spots": result["spots"],
    }
