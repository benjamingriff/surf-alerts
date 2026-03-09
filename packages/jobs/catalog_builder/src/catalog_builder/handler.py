from datetime import datetime, timezone
from urllib.parse import unquote_plus

import pyarrow as pa
from aws_lambda_powertools.utilities.typing import LambdaContext

from catalog_builder.logger import get_logger, inject_lambda_context
from catalog_builder.s3 import S3Client

logger = get_logger()
s3_client = S3Client()
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


def _parse_s3_reference(event: dict) -> tuple[str, str]:
    if "detail" in event:
        return event["detail"]["bucket"]["name"], unquote_plus(event["detail"]["object"]["key"])

    record = event["Records"][0]
    return record["s3"]["bucket"]["name"], unquote_plus(record["s3"]["object"]["key"])


def _checkpoint_key(discovery_run_id: str) -> str:
    return f"control/checkpoints/catalog_builder/run_id={discovery_run_id}.json.gz"


def _parse_timestamp(value):
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def _latest_active_core_rows(core_rows: list[dict]) -> list[dict]:
    latest_by_spot_id: dict[str, dict] = {}
    for row in core_rows:
        spot_id = row["spot_id"]
        current = latest_by_spot_id.get(spot_id)
        if current is None or _parse_timestamp(row["version_ts"]) > _parse_timestamp(current["version_ts"]):
            latest_by_spot_id[spot_id] = row
    return sorted(
        [row for row in latest_by_spot_id.values() if row.get("event_type") != "removed"],
        key=lambda row: row["spot_id"],
    )


@inject_lambda_context(log_event=False)
def lambda_handler(event: dict, context: LambdaContext):
    bucket, key = _parse_s3_reference(event)
    manifest = s3_client.get_json(bucket, key)
    if manifest is None:
        raise FileNotFoundError(f"Missing processing manifest: s3://{bucket}/{key}")

    checkpoint_key = _checkpoint_key(manifest["discovery_run_id"])
    if s3_client.object_exists(bucket, checkpoint_key):
        logger.info("Catalog already built for run", extra={"discovery_run_id": manifest["discovery_run_id"]})
        return {"statusCode": 200, "body": "duplicate catalog build ignored"}

    core_rows = s3_client.read_parquet_prefix(bucket, "processed/discovery/dim_spots_core/")
    latest_core_rows = _latest_active_core_rows(core_rows)
    active_version_ids = {row["spot_version_id"] for row in latest_core_rows}

    snapshot_rows = {
        "dim_spots_core": latest_core_rows,
        "dim_spot_location": [
            row
            for row in s3_client.read_parquet_prefix(bucket, "processed/discovery/dim_spot_location/")
            if row["spot_version_id"] in active_version_ids
        ],
        "dim_spot_breadcrumbs": [
            row
            for row in s3_client.read_parquet_prefix(bucket, "processed/discovery/dim_spot_breadcrumbs/")
            if row["spot_version_id"] in active_version_ids
        ],
        "dim_spot_cameras": [
            row
            for row in s3_client.read_parquet_prefix(bucket, "processed/discovery/dim_spot_cameras/")
            if row["spot_version_id"] in active_version_ids
        ],
        "dim_spot_ability_levels": [
            row
            for row in s3_client.read_parquet_prefix(bucket, "processed/discovery/dim_spot_ability_levels/")
            if row["spot_version_id"] in active_version_ids
        ],
        "dim_spot_board_types": [
            row
            for row in s3_client.read_parquet_prefix(bucket, "processed/discovery/dim_spot_board_types/")
            if row["spot_version_id"] in active_version_ids
        ],
        "dim_spot_travel_details": [
            row
            for row in s3_client.read_parquet_prefix(bucket, "processed/discovery/dim_spot_travel_details/")
            if row["spot_version_id"] in active_version_ids
        ],
    }

    for table_name, rows in snapshot_rows.items():
        s3_client.write_parquet(
            bucket,
            f"processed/discovery/catalog_latest/{table_name}.parquet",
            rows,
            TABLE_SCHEMAS[table_name],
        )

    s3_client.put_json(
        bucket,
        "control/checkpoints/discovery/latest.json.gz",
        {
            "schema_version": SCHEMA_VERSION,
            "discovery_run_id": manifest["discovery_run_id"],
            "built_at": _utc_now().isoformat(),
            "active_spot_count": len(latest_core_rows),
        },
    )
    s3_client.put_json(
        bucket,
        checkpoint_key,
        {
            "schema_version": SCHEMA_VERSION,
            "discovery_run_id": manifest["discovery_run_id"],
            "built_at": _utc_now().isoformat(),
        },
    )
    return {"statusCode": 200, "body": "catalog latest rebuilt"}
