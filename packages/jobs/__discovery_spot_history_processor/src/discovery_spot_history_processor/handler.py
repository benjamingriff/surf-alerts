import json
import os
from datetime import datetime, timezone

import boto3
from aws_lambda_powertools.utilities.typing import LambdaContext

from discovery_control import (
    ControlStore,
    RUN_STATUS_CATALOG_BUILD_READY,
    RUN_STATUS_SPOT_HISTORY_IN_PROGRESS,
)
from discovery_spot_history_processor.logger import get_logger, inject_lambda_context
from discovery_spot_history_processor.s3 import S3Client

logger = get_logger()
s3_client = S3Client()
store = ControlStore()
sqs_client = boto3.client("sqs")

SCHEMA_VERSION = 1


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _table_key(table_name: str, scrape_date: str, discovery_run_id: str, chunk_id: str) -> str:
    year, month, _ = scrape_date.split("-")
    return (
        f"processed/discovery/{table_name}/year={year}/month={month}/"
        f"discovery_run_id={discovery_run_id}/chunk_id={chunk_id}.parquet"
    )


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


def _resolve_links(sitemap_payload: dict, spot_id: str) -> tuple[str | None, str | None]:
    spot = sitemap_payload.get("spots", {}).get(spot_id, {})
    return spot.get("link"), spot.get("forecast")


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
        "spot_version_id": f"{canonical_spot['spot_id']}::{raw_envelope['run_id']}",
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


def _catalog_build_queue_url() -> str:
    return os.environ["DISCOVERY_CATALOG_BUILD_QUEUE_URL"]


@inject_lambda_context(log_event=False)
def lambda_handler(event: dict, context: LambdaContext):
    processed = 0
    for record in event["Records"]:
        payload = json.loads(record["body"])
        discovery_run_id = payload["discovery_run_id"]
        chunk_id = payload["chunk_id"]

        run = store.get_run(discovery_run_id)
        if run is None:
            raise FileNotFoundError(f"Missing discovery run state: {discovery_run_id}")
        chunk = store.get_chunk(discovery_run_id, chunk_id)
        if chunk is None:
            raise FileNotFoundError(f"Missing discovery chunk state: {discovery_run_id}/{chunk_id}")
        if chunk.get("status") == "complete":
            continue

        sitemap_payload = s3_client.get_json(os.environ["DATA_BUCKET"], run["sitemap_raw_key"])
        if sitemap_payload is None:
            raise FileNotFoundError(
                f"Missing raw sitemap payload: s3://{os.environ['DATA_BUCKET']}/{run['sitemap_raw_key']}"
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

        for spot_id, raw_key in zip(chunk["spot_ids"], chunk["raw_keys"], strict=True):
            raw_envelope = s3_client.get_json(os.environ["DATA_BUCKET"], raw_key)
            if raw_envelope is None:
                raise FileNotFoundError(f"Missing raw spot report: s3://{os.environ['DATA_BUCKET']}/{raw_key}")

            version_ts = datetime.fromisoformat(raw_envelope["scraped_at"].replace("Z", "+00:00"))
            canonical_spot = _canonicalize_spot(raw_envelope["raw_payload"], spot_id)
            sitemap_link, forecast_link = _resolve_links(sitemap_payload, spot_id)
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
            table_key = _table_key(table_name, run["scrape_date"], discovery_run_id, chunk_id)
            s3_client.put_parquet(os.environ["DATA_BUCKET"], table_key, rows)
            written_keys.append(table_key)

        newly_completed = store.mark_chunk_complete(
            discovery_run_id=discovery_run_id,
            chunk_id=chunk_id,
            output_keys=written_keys,
        )
        if not newly_completed:
            continue

        run = store.get_run(discovery_run_id)
        if (
            run is not None
            and run["completed_chunk_count"] == run["chunk_count"]
            and store.transition_run_status(
                discovery_run_id=discovery_run_id,
                from_status=RUN_STATUS_SPOT_HISTORY_IN_PROGRESS,
                to_status=RUN_STATUS_CATALOG_BUILD_READY,
            )
        ):
            sqs_client.send_message(
                QueueUrl=_catalog_build_queue_url(),
                MessageBody=json.dumps({"discovery_run_id": discovery_run_id}),
            )

        processed += 1

    return {"statusCode": 200, "body": f"processed {processed} chunk(s)"}
