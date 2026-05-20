import json
import os
from datetime import datetime, timezone

import pyarrow as pa
from aws_lambda_powertools.utilities.typing import LambdaContext

from discovery_catalog_builder.logger import get_logger, inject_lambda_context
from discovery_catalog_builder.s3 import S3Client
from discovery_control import ControlStore, RUN_STATUS_CATALOG_BUILD_READY, RUN_STATUS_CATALOG_COMPLETE

logger = get_logger()
s3_client = S3Client()
store = ControlStore()
SCHEMA_VERSION = 1

TABLE_SCHEMAS = {
    "dim_spots_core": pa.schema(
        [
            ("spot_version_id", pa.string()),
            ("spot_id", pa.string()),
            ("version_ts", pa.timestamp("us", tz="UTC")),
            ("content_checksum", pa.string()),
            ("event_type", pa.string()),
            ("seen_at", pa.timestamp("us", tz="UTC")),
            ("sitemap_link", pa.string()),
            ("forecast_link", pa.string()),
            ("source_run_id", pa.string()),
            ("source_raw_key", pa.string()),
            ("source_type", pa.string()),
            ("schema_version", pa.int64()),
            ("processed_at", pa.timestamp("us", tz="UTC")),
        ]
    ),
    "dim_spot_location": pa.schema(
        [
            ("spot_version_id", pa.string()),
            ("spot_id", pa.string()),
            ("name", pa.string()),
            ("lat", pa.float64()),
            ("lon", pa.float64()),
            ("timezone", pa.string()),
            ("utc_offset", pa.int64()),
            ("abbr_timezone", pa.string()),
            ("subregion_id", pa.string()),
            ("subregion_name", pa.string()),
        ]
    ),
    "dim_spot_breadcrumbs": pa.schema(
        [
            ("spot_version_id", pa.string()),
            ("spot_id", pa.string()),
            ("breadcrumb_index", pa.int64()),
            ("name", pa.string()),
            ("href", pa.string()),
        ]
    ),
    "dim_spot_cameras": pa.schema(
        [
            ("spot_version_id", pa.string()),
            ("spot_id", pa.string()),
            ("camera_index", pa.int64()),
            ("camera_id", pa.string()),
            ("title", pa.string()),
            ("stream_url", pa.string()),
            ("still_url", pa.string()),
            ("is_premium", pa.bool_()),
        ]
    ),
    "dim_spot_ability_levels": pa.schema(
        [
            ("spot_version_id", pa.string()),
            ("spot_id", pa.string()),
            ("ability_index", pa.int64()),
            ("ability_level", pa.string()),
        ]
    ),
    "dim_spot_board_types": pa.schema(
        [
            ("spot_version_id", pa.string()),
            ("spot_id", pa.string()),
            ("board_type_index", pa.int64()),
            ("board_type", pa.string()),
        ]
    ),
    "dim_spot_travel_details": pa.schema(
        [
            ("spot_version_id", pa.string()),
            ("spot_id", pa.string()),
            ("description", pa.string()),
            ("access", pa.string()),
            ("hazards", pa.string()),
            ("best_size", pa.string()),
            ("crowd_factor", pa.string()),
            ("spot_rating", pa.int64()),
            ("break_types_json", pa.string()),
            ("best_seasons_json", pa.string()),
            ("best_tides_json", pa.string()),
            ("best_swell_directions_json", pa.string()),
            ("best_wind_directions_json", pa.string()),
            ("bottom_json", pa.string()),
        ]
    ),
}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_timestamp(value):
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def _read_latest(bucket: str, table_name: str) -> list[dict]:
    key = f"processed/discovery/catalog_latest/{table_name}.parquet"
    if not s3_client.object_exists(bucket, key):
        return []
    return s3_client.read_parquet_object(bucket, key)


def _append_chunk_rows(bucket: str, table_name: str, chunk_output_keys: list[str]) -> list[dict]:
    rows: list[dict] = []
    prefix = f"processed/discovery/{table_name}/"
    for key in chunk_output_keys:
        if key.startswith(prefix):
            rows.extend(s3_client.read_parquet_object(bucket, key))
    return rows


@inject_lambda_context(log_event=False)
def lambda_handler(event: dict, context: LambdaContext):
    processed = 0
    for record in event["Records"]:
        payload = json.loads(record["body"])
        discovery_run_id = payload["discovery_run_id"]
        run = store.get_run(discovery_run_id)
        if run is None:
            raise FileNotFoundError(f"Missing discovery run state: {discovery_run_id}")
        if run["status"] == RUN_STATUS_CATALOG_COMPLETE:
            continue
        if run["status"] != RUN_STATUS_CATALOG_BUILD_READY:
            raise ValueError(f"Unexpected catalog build status: {run['status']}")

        bucket = record.get("bucket") or payload.get("bucket") or payload.get("data_bucket") or os.environ["DATA_BUCKET"]
        removed_spot_ids = set(run.get("removed_spot_ids", []))
        completed_chunks = store.list_chunks(discovery_run_id, status="complete")
        chunk_output_keys = [key for chunk in completed_chunks for key in chunk.get("output_keys", [])]
        successful_spot_ids = {spot["spot_id"] for spot in store.list_spots(discovery_run_id, terminal_status="success")}
        affected_spot_ids = removed_spot_ids | successful_spot_ids

        snapshot_rows = {}
        for table_name in TABLE_SCHEMAS:
            current_rows = _read_latest(bucket, table_name)
            filtered_rows = [row for row in current_rows if row.get("spot_id") not in affected_spot_ids]
            new_rows = _append_chunk_rows(bucket, table_name, chunk_output_keys)
            snapshot_rows[table_name] = filtered_rows + new_rows

        for table_name, rows in snapshot_rows.items():
            s3_client.write_parquet(
                bucket,
                f"processed/discovery/catalog_latest/{table_name}.parquet",
                rows,
                TABLE_SCHEMAS[table_name],
            )

        if not store.set_run_catalog_complete(discovery_run_id):
            logger.info("Catalog already completed", extra={"discovery_run_id": discovery_run_id})
            continue

        logger.info(
            "Discovery catalog latest rebuilt",
            extra={
                "discovery_run_id": discovery_run_id,
                "active_spot_count": len(snapshot_rows["dim_spots_core"]),
            },
        )
        processed += 1

    return {"statusCode": 200, "body": f"catalog builds processed: {processed}"}
