import json
from datetime import datetime, timezone
from urllib.parse import unquote_plus
from uuid import uuid4

from aws_lambda_powertools.utilities.typing import LambdaContext

from discovery_spot_history_processor.logger import get_logger, inject_lambda_context
from discovery_spot_history_processor.s3 import S3Client

logger = get_logger()
s3_client = S3Client()

CATALOG_CORE_KEY = "processed/discovery/catalog_latest/dim_spots_core.parquet"
SCHEMA_VERSION = 1


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_s3_reference(event: dict) -> tuple[str, str]:
    if "detail" in event:
        return event["detail"]["bucket"]["name"], unquote_plus(event["detail"]["object"]["key"])

    record = event["Records"][0]
    return record["s3"]["bucket"]["name"], unquote_plus(record["s3"]["object"]["key"])


def _checkpoint_key(discovery_run_id: str) -> str:
    return f"control/checkpoints/discovery_spot_history_processor/discovery_run_id={discovery_run_id}.json.gz"


def _catalog_build_manifest_key(scrape_date: str, discovery_run_id: str) -> str:
    return (
        "control/manifests/processing/"
        f"domain=discovery/stage=catalog_build/date={scrape_date}/discovery_run_id={discovery_run_id}.json.gz"
    )


def _table_key(table_name: str, scrape_date: str, discovery_run_id: str) -> str:
    year, month, _ = scrape_date.split("-")
    return f"processed/discovery/{table_name}/year={year}/month={month}/discovery_run_id={discovery_run_id}.parquet"


def _normalize_optional_list(values) -> list:
    if not values:
        return []
    return list(values)


def _normalize_breadcrumbs(values) -> list[dict]:
    breadcrumbs = []
    for item in values or []:
        if isinstance(item, dict):
            breadcrumbs.append({"name": item.get("name"), "href": item.get("href")})
        else:
            breadcrumbs.append({"name": item, "href": None})
    return breadcrumbs


def _parse_travel_details(details: dict | None) -> dict | None:
    if not details:
        return None
    return {
        "description": details.get("description"),
        "access": details.get("access"),
        "hazards": details.get("hazards"),
        "best_size": details.get("best", {}).get("size", {}).get("description"),
        "crowd_factor": details.get("crowdFactor", {}).get("summary"),
        "spot_rating": details.get("spotRating", {}).get("rating"),
        "break_types": _normalize_optional_list(details.get("breakType", [])),
        "best_seasons": _normalize_optional_list(details.get("best", {}).get("season", {}).get("value", [])),
        "best_tides": _normalize_optional_list(details.get("best", {}).get("tide", {}).get("value", [])),
        "best_swell_directions": _normalize_optional_list(
            details.get("best", {}).get("swellDirection", {}).get("value", [])
        ),
        "best_wind_directions": _normalize_optional_list(
            details.get("best", {}).get("windDirection", {}).get("value", [])
        ),
        "bottom": _normalize_optional_list(details.get("bottom", {}).get("value", [])),
    }


def _canonicalize_spot(raw_payload: dict, spot_id: str) -> dict:
    spot = raw_payload.get("spot", {})
    associated = raw_payload.get("associated", {})
    subregion = spot.get("subregion")
    if isinstance(subregion, dict):
        subregion_id = subregion.get("_id") or subregion.get("id")
        subregion_name = subregion.get("name")
    else:
        subregion_id = None
        subregion_name = subregion

    return {
        "spot_id": spot_id,
        "name": spot.get("name"),
        "lat": spot.get("lat"),
        "lon": spot.get("lon"),
        "timezone": associated.get("timezone"),
        "utc_offset": associated.get("utcOffset"),
        "abbr_timezone": associated.get("abbrTimezone"),
        "href": associated.get("href"),
        "forecast_link": associated.get("forecastLink"),
        "breadcrumbs": _normalize_breadcrumbs(spot.get("breadcrumb")),
        "subregion_id": subregion_id,
        "subregion_name": subregion_name,
        "cameras": [
            {
                "camera_id": camera.get("_id"),
                "title": camera.get("title"),
                "stream_url": camera.get("streamUrl"),
                "still_url": camera.get("stillUrl"),
                "is_premium": camera.get("isPremium"),
            }
            for camera in spot.get("cameras", [])
        ],
        "ability_levels": _normalize_optional_list(spot.get("abilityLevels", [])),
        "board_types": _normalize_optional_list(spot.get("boardTypes", [])),
        "travel_details": _parse_travel_details(spot.get("travelDetails")),
    }


def _resolve_links(bucket: str, raw_envelope: dict, spot_id: str) -> tuple[str | None, str | None]:
    sitemap_link = None
    forecast_link = None
    source_raw_key = raw_envelope.get("source_raw_key")
    if source_raw_key:
        sitemap_payload = s3_client.get_json(bucket, source_raw_key)
        if sitemap_payload:
            spot = sitemap_payload.get("spots", {}).get(spot_id, {})
            sitemap_link = spot.get("link")
            forecast_link = spot.get("forecast")
    return sitemap_link, forecast_link


def _build_core_row(
    *,
    canonical_spot: dict,
    version_ts: datetime,
    raw_envelope: dict,
    raw_key: str,
    sitemap_link: str | None,
    forecast_link: str | None,
) -> dict:
    return {
        "spot_version_id": str(uuid4()),
        "spot_id": canonical_spot["spot_id"],
        "version_ts": version_ts,
        "content_checksum": None,
        "event_type": "added",
        "seen_at": datetime.fromisoformat(raw_envelope["scraped_at"].replace("Z", "+00:00")),
        "sitemap_link": sitemap_link,
        "forecast_link": forecast_link,
        "source_run_id": raw_envelope["run_id"],
        "source_raw_key": raw_key,
        "source_type": "spot_report",
        "schema_version": SCHEMA_VERSION,
        "processed_at": _utc_now(),
    }


def _build_child_rows(canonical_spot: dict, spot_version_id: str) -> dict[str, list[dict]]:
    travel_details = canonical_spot.get("travel_details")
    return {
        "dim_spot_location": [
            {
                "spot_version_id": spot_version_id,
                "spot_id": canonical_spot["spot_id"],
                "name": canonical_spot.get("name"),
                "lat": canonical_spot.get("lat"),
                "lon": canonical_spot.get("lon"),
                "timezone": canonical_spot.get("timezone"),
                "utc_offset": canonical_spot.get("utc_offset"),
                "abbr_timezone": canonical_spot.get("abbr_timezone"),
                "subregion_id": canonical_spot.get("subregion_id"),
                "subregion_name": canonical_spot.get("subregion_name"),
            }
        ],
        "dim_spot_breadcrumbs": [
            {
                "spot_version_id": spot_version_id,
                "spot_id": canonical_spot["spot_id"],
                "breadcrumb_index": index,
                "name": item.get("name"),
                "href": item.get("href"),
            }
            for index, item in enumerate(canonical_spot.get("breadcrumbs", []))
        ],
        "dim_spot_cameras": [
            {
                "spot_version_id": spot_version_id,
                "spot_id": canonical_spot["spot_id"],
                "camera_index": index,
                "camera_id": item.get("camera_id"),
                "title": item.get("title"),
                "stream_url": item.get("stream_url"),
                "still_url": item.get("still_url"),
                "is_premium": item.get("is_premium"),
            }
            for index, item in enumerate(canonical_spot.get("cameras", []))
        ],
        "dim_spot_ability_levels": [
            {
                "spot_version_id": spot_version_id,
                "spot_id": canonical_spot["spot_id"],
                "ability_index": index,
                "ability_level": value,
            }
            for index, value in enumerate(canonical_spot.get("ability_levels", []))
        ],
        "dim_spot_board_types": [
            {
                "spot_version_id": spot_version_id,
                "spot_id": canonical_spot["spot_id"],
                "board_type_index": index,
                "board_type": value,
            }
            for index, value in enumerate(canonical_spot.get("board_types", []))
        ],
        "dim_spot_travel_details": []
        if not travel_details
        else [
            {
                "spot_version_id": spot_version_id,
                "spot_id": canonical_spot["spot_id"],
                "description": travel_details.get("description"),
                "access": travel_details.get("access"),
                "hazards": travel_details.get("hazards"),
                "best_size": travel_details.get("best_size"),
                "crowd_factor": travel_details.get("crowd_factor"),
                "spot_rating": travel_details.get("spot_rating"),
                "break_types_json": json.dumps(travel_details.get("break_types", [])),
                "best_seasons_json": json.dumps(travel_details.get("best_seasons", [])),
                "best_tides_json": json.dumps(travel_details.get("best_tides", [])),
                "best_swell_directions_json": json.dumps(travel_details.get("best_swell_directions", [])),
                "best_wind_directions_json": json.dumps(travel_details.get("best_wind_directions", [])),
                "bottom_json": json.dumps(travel_details.get("bottom", [])),
            }
        ],
    }


@inject_lambda_context(log_event=False)
def lambda_handler(event: dict, context: LambdaContext):
    bucket, key = _parse_s3_reference(event)
    manifest = s3_client.get_json(bucket, key)
    if manifest is None:
        raise FileNotFoundError(f"Missing processing manifest: s3://{bucket}/{key}")
    if manifest.get("stage") != "spot_history":
        raise ValueError(f"Unexpected processing stage: {manifest.get('stage')}")

    checkpoint_key = _checkpoint_key(manifest["discovery_run_id"])
    if s3_client.object_exists(bucket, checkpoint_key):
        logger.info("Spot history already built", extra={"discovery_run_id": manifest["discovery_run_id"]})
        return {"statusCode": 200, "body": "duplicate spot history build ignored"}

    latest_rows = s3_client.get_parquet_rows(bucket, CATALOG_CORE_KEY)
    latest_by_spot_id = {row["spot_id"]: row for row in latest_rows if row.get("event_type") != "removed"}
    existing_spot_ids = sorted(spot_id for spot_id in manifest["spot_ids"] if spot_id in latest_by_spot_id)
    if existing_spot_ids:
        raise ValueError(f"Discovery run contains already-active spot IDs: {existing_spot_ids}")

    logger.info(
        "Building discovery spot history",
        extra={
            "discovery_run_id": manifest["discovery_run_id"],
            "successful_spot_count": len(manifest.get("spot_ids", [])),
            "failed_spot_count": manifest.get("failed_spot_count", 0),
        },
    )

    table_rows = {
        "dim_spots_core": [],
        "dim_spot_location": [],
        "dim_spot_breadcrumbs": [],
        "dim_spot_cameras": [],
        "dim_spot_ability_levels": [],
        "dim_spot_board_types": [],
        "dim_spot_travel_details": [],
    }

    for spot_id, raw_key in zip(manifest["spot_ids"], manifest["raw_keys"], strict=True):
        raw_envelope = s3_client.get_json(bucket, raw_key)
        if raw_envelope is None:
            raise FileNotFoundError(f"Missing raw spot report: s3://{bucket}/{raw_key}")

        version_ts = datetime.fromisoformat(raw_envelope["scraped_at"].replace("Z", "+00:00"))
        canonical_spot = _canonicalize_spot(raw_envelope["raw_payload"], spot_id)
        sitemap_link, forecast_link = _resolve_links(bucket=bucket, raw_envelope=raw_envelope, spot_id=spot_id)
        core_row = _build_core_row(
            canonical_spot=canonical_spot,
            version_ts=version_ts,
            raw_envelope=raw_envelope,
            raw_key=raw_key,
            sitemap_link=sitemap_link,
            forecast_link=forecast_link,
        )
        table_rows["dim_spots_core"].append(core_row)
        child_rows = _build_child_rows(canonical_spot, core_row["spot_version_id"])
        for table_name, rows in child_rows.items():
            table_rows[table_name].extend(rows)

    written_keys = []
    for table_name, rows in table_rows.items():
        if not rows:
            continue
        table_key = _table_key(table_name, manifest["scrape_date"], manifest["discovery_run_id"])
        s3_client.put_parquet(bucket, table_key, rows)
        written_keys.append(table_key)

    s3_client.put_json(
        bucket,
        _catalog_build_manifest_key(manifest["scrape_date"], manifest["discovery_run_id"]),
        {
            "schema_version": SCHEMA_VERSION,
            "manifest_type": "processing_manifest",
            "domain": "discovery",
            "stage": "catalog_build",
            "discovery_run_id": manifest["discovery_run_id"],
            "scrape_date": manifest["scrape_date"],
            "source_manifest_key": key,
            "source_keys": written_keys,
            "failed_spot_ids": manifest.get("failed_spot_ids", []),
            "failed_spot_count": manifest.get("failed_spot_count", 0),
            "ready_at": _utc_now().isoformat(),
        },
    )
    s3_client.put_json(
        bucket,
        checkpoint_key,
        {
            "schema_version": SCHEMA_VERSION,
            "discovery_run_id": manifest["discovery_run_id"],
            "processed_at": _utc_now().isoformat(),
        },
    )
    return {"statusCode": 200, "body": "discovery spot history built"}
