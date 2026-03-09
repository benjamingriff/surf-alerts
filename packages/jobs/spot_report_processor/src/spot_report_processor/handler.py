import hashlib
import json
from datetime import datetime, timezone
from urllib.parse import unquote_plus
from uuid import uuid4

from aws_lambda_powertools.utilities.typing import LambdaContext

from spot_report_processor.logger import get_logger, inject_lambda_context
from spot_report_processor.s3 import S3Client

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


def _checkpoint_key(run_id: str) -> str:
    return f"control/checkpoints/spot_report_processor/raw_run_id={run_id}.json.gz"


def _completion_key(scrape_date: str, discovery_run_id: str, spot_id: str) -> str:
    return (
        "control/manifests/discovery_runs/"
        f"date={scrape_date}/run_id={discovery_run_id}/completed/spot_id={spot_id}.json.gz"
    )


def _events_key(event_ts: datetime) -> str:
    return (
        "processed/discovery/events/"
        f"year={event_ts:%Y}/month={event_ts:%m}/event_date={event_ts:%Y-%m-%d}/"
        f"part-{uuid4()}.parquet"
    )


def _table_key(table_name: str, ts: datetime) -> str:
    return f"processed/discovery/{table_name}/year={ts:%Y}/month={ts:%m}/part-{uuid4()}.parquet"


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


def _checksum(canonical_spot: dict) -> str:
    payload = json.dumps(canonical_spot, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _resolve_links(bucket: str, raw_envelope: dict, latest_row: dict | None, spot_id: str) -> tuple[str | None, str | None]:
    sitemap_link = latest_row.get("sitemap_link") if latest_row else None
    forecast_link = latest_row.get("forecast_link") if latest_row else None

    source_raw_key = raw_envelope.get("source_raw_key")
    if source_raw_key:
        sitemap_payload = s3_client.get_json(bucket, source_raw_key)
        if sitemap_payload:
            spot = sitemap_payload.get("spots", {}).get(spot_id, {})
            sitemap_link = spot.get("link", sitemap_link)
            forecast_link = spot.get("forecast", forecast_link)

    return sitemap_link, forecast_link


def _build_core_row(
    *,
    canonical_spot: dict,
    checksum: str,
    version_ts: datetime,
    raw_envelope: dict,
    raw_key: str,
    event_type: str,
    sitemap_link: str | None,
    forecast_link: str | None,
) -> dict:
    return {
        "spot_version_id": str(uuid4()),
        "spot_id": canonical_spot["spot_id"],
        "version_ts": version_ts,
        "content_checksum": checksum,
        "event_type": event_type,
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
                "best_swell_directions_json": json.dumps(
                    travel_details.get("best_swell_directions", [])
                ),
                "best_wind_directions_json": json.dumps(
                    travel_details.get("best_wind_directions", [])
                ),
                "bottom_json": json.dumps(travel_details.get("bottom", [])),
            }
        ],
    }


def _build_changed_event(
    *,
    spot_id: str,
    raw_key: str,
    raw_run_id: str,
    old_checksum: str | None,
    new_checksum: str,
    spot_version_id: str,
    version_ts: datetime,
) -> dict:
    return {
        "event_ts": version_ts,
        "run_id": raw_run_id,
        "spot_id": spot_id,
        "event_type": "changed",
        "source_type": "spot_report",
        "source_raw_key": raw_key,
        "old_checksum": old_checksum,
        "new_checksum": new_checksum,
        "spot_version_id": spot_version_id,
        "version_ts": version_ts,
    }


@inject_lambda_context(log_event=False)
def lambda_handler(event: dict, context: LambdaContext):
    bucket, raw_key = _parse_s3_reference(event)
    raw_envelope = s3_client.get_json(bucket, raw_key)
    if raw_envelope is None:
        raise FileNotFoundError(f"Missing raw spot report: s3://{bucket}/{raw_key}")

    checkpoint_key = _checkpoint_key(raw_envelope["run_id"])
    if s3_client.object_exists(bucket, checkpoint_key):
        logger.info("Spot report already processed", extra={"checkpoint_key": checkpoint_key})
        return {"statusCode": 200, "body": "duplicate spot-report event ignored"}

    latest_rows = s3_client.get_parquet_rows(bucket, CATALOG_CORE_KEY)
    latest_by_spot_id = {row["spot_id"]: row for row in latest_rows}
    latest_row = latest_by_spot_id.get(raw_envelope["spot_id"])

    canonical_spot = _canonicalize_spot(raw_envelope["raw_payload"], raw_envelope["spot_id"])
    checksum = _checksum(canonical_spot)
    if latest_row and latest_row.get("content_checksum") == checksum:
        logger.info("Checksum unchanged", extra={"spot_id": raw_envelope["spot_id"]})
    else:
        version_ts = _utc_now()
        event_type = "added" if not latest_row or latest_row.get("event_type") == "removed" else "changed"
        sitemap_link, forecast_link = _resolve_links(
            bucket=bucket,
            raw_envelope=raw_envelope,
            latest_row=latest_row,
            spot_id=raw_envelope["spot_id"],
        )
        core_row = _build_core_row(
            canonical_spot=canonical_spot,
            checksum=checksum,
            version_ts=version_ts,
            raw_envelope=raw_envelope,
            raw_key=raw_key,
            event_type=event_type,
            sitemap_link=sitemap_link,
            forecast_link=forecast_link,
        )
        s3_client.put_parquet(bucket, _table_key("dim_spots_core", version_ts), [core_row])
        for table_name, rows in _build_child_rows(canonical_spot, core_row["spot_version_id"]).items():
            s3_client.put_parquet(bucket, _table_key(table_name, version_ts), rows)
        if event_type == "changed":
            s3_client.put_parquet(
                bucket,
                _events_key(version_ts),
                [
                    _build_changed_event(
                        spot_id=raw_envelope["spot_id"],
                        raw_key=raw_key,
                        raw_run_id=raw_envelope["run_id"],
                        old_checksum=latest_row.get("content_checksum") if latest_row else None,
                        new_checksum=checksum,
                        spot_version_id=core_row["spot_version_id"],
                        version_ts=version_ts,
                    )
                ],
            )

    scrape_date = raw_envelope["scraped_at"][:10]
    if raw_envelope.get("discovery_run_id"):
        s3_client.put_json(
            bucket,
            _completion_key(
                scrape_date=scrape_date,
                discovery_run_id=raw_envelope["discovery_run_id"],
                spot_id=raw_envelope["spot_id"],
            ),
            {
                "schema_version": SCHEMA_VERSION,
                "discovery_run_id": raw_envelope["discovery_run_id"],
                "spot_id": raw_envelope["spot_id"],
                "raw_run_id": raw_envelope["run_id"],
                "raw_key": raw_key,
                "processed_at": _utc_now().isoformat(),
            },
        )

    s3_client.put_json(
        bucket,
        checkpoint_key,
        {
            "schema_version": SCHEMA_VERSION,
            "raw_run_id": raw_envelope["run_id"],
            "raw_key": raw_key,
            "processed_at": _utc_now().isoformat(),
        },
    )
    return {"statusCode": 200, "body": "spot report processed"}
