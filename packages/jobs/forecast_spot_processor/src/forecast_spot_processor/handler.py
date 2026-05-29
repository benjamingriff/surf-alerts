import gzip
import json
import logging
from typing import Any

import boto3
from forecast_control import ForecastControlStore
from forecast_transform import ForecastRows, transform_forecast_envelope
from postgres_client import connect

logger = logging.getLogger(__name__)

TABLE_COLUMNS = {
    "forecast_fact_rating": [
        "forecast_run_id",
        "spot_id",
        "spot_version_id",
        "forecast_ts",
        "scraped_at",
        "scheduled_utc_time",
        "utc_offset",
        "timezone",
        "rating_key",
        "rating_value",
        "source_utc_offset",
        "run_init_ts",
        "source_raw_key",
        "schema_version",
    ],
    "forecast_fact_wave": [
        "forecast_run_id",
        "spot_id",
        "spot_version_id",
        "forecast_ts",
        "scraped_at",
        "scheduled_utc_time",
        "utc_offset",
        "timezone",
        "surf_min",
        "surf_max",
        "surf_plus",
        "surf_human_relation",
        "surf_raw_min",
        "surf_raw_max",
        "surf_optimal_score",
        "power",
        "probability",
        "source_utc_offset",
        "location_lon",
        "location_lat",
        "forecast_location_lon",
        "forecast_location_lat",
        "offshore_location_lon",
        "offshore_location_lat",
        "run_init_ts",
        "source_raw_key",
        "schema_version",
    ],
    "forecast_fact_swells": [
        "forecast_run_id",
        "spot_id",
        "spot_version_id",
        "forecast_ts",
        "swell_index",
        "scraped_at",
        "scheduled_utc_time",
        "utc_offset",
        "timezone",
        "height",
        "period",
        "impact",
        "power",
        "direction",
        "direction_min",
        "optimal_score",
        "source_raw_key",
        "schema_version",
    ],
    "forecast_fact_wind": [
        "forecast_run_id",
        "spot_id",
        "spot_version_id",
        "forecast_ts",
        "scraped_at",
        "scheduled_utc_time",
        "utc_offset",
        "timezone",
        "speed",
        "gust",
        "direction",
        "direction_type",
        "optimal_score",
        "source_utc_offset",
        "location_lon",
        "location_lat",
        "run_init_ts",
        "source_raw_key",
        "schema_version",
    ],
    "forecast_fact_tides": [
        "forecast_run_id",
        "spot_id",
        "spot_version_id",
        "forecast_ts",
        "tide_index",
        "scraped_at",
        "scheduled_utc_time",
        "utc_offset",
        "timezone",
        "tide_type",
        "height",
        "source_utc_offset",
        "tide_location_name",
        "tide_location_lon",
        "tide_location_lat",
        "tide_location_min",
        "tide_location_max",
        "tide_location_mean",
        "source_raw_key",
        "schema_version",
    ],
}

CONFLICT_TARGETS = {
    "forecast_fact_rating": "scheduled_utc_time, forecast_run_id, spot_id, forecast_ts",
    "forecast_fact_wave": "scheduled_utc_time, forecast_run_id, spot_id, forecast_ts",
    "forecast_fact_swells": "scheduled_utc_time, forecast_run_id, spot_id, forecast_ts, swell_index",
    "forecast_fact_wind": "scheduled_utc_time, forecast_run_id, spot_id, forecast_ts",
    "forecast_fact_tides": "scheduled_utc_time, forecast_run_id, spot_id, forecast_ts, tide_index",
}


def _s3_client():
    return boto3.client("s3")


def _store() -> ForecastControlStore:
    return ForecastControlStore()


def _get_json(bucket: str, key: str) -> dict[str, Any]:
    data = _s3_client().get_object(Bucket=bucket, Key=key)["Body"].read()
    if key.endswith(".gz"):
        data = gzip.decompress(data)
    return json.loads(data)


def _insert_table(cur, table: str, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    columns = TABLE_COLUMNS[table]
    sql = (
        f"insert into {table} ({','.join(columns)}) values ({','.join(['%s'] * len(columns))}) "
        f"on conflict ({CONFLICT_TARGETS[table]}) do nothing"
    )
    cur.executemany(sql, [[row.get(column) for column in columns] for row in rows])


def insert_forecast_rows(conn, rows: ForecastRows) -> None:
    with conn.transaction():
        with conn.cursor() as cur:
            _insert_table(cur, "forecast_fact_rating", rows.ratings)
            _insert_table(cur, "forecast_fact_wave", rows.waves)
            _insert_table(cur, "forecast_fact_swells", rows.swells)
            _insert_table(cur, "forecast_fact_wind", rows.winds)
            _insert_table(cur, "forecast_fact_tides", rows.tides)


def process_completion(
    message: dict[str, Any], *, store: ForecastControlStore | None = None, connection=None
) -> str:
    store = store or _store()
    run_id = message["forecast_run_id"]
    spot_id = message["spot_id"]
    scrape_status = message.get("scrape_status")

    recorded = store.record_scrape_terminal(
        forecast_run_id=run_id,
        spot_id=spot_id,
        scrape_status=scrape_status,
        raw_bucket=message.get("raw_bucket"),
        raw_key=message.get("raw_key"),
        scraped_at=message.get("scraped_at"),
        failure_source=message.get("failure_source"),
        failure_reason=message.get("failure_reason"),
    )

    if scrape_status != "success":
        store.update_run_rollup(run_id)
        return "scrape_failed" if recorded else "duplicate"

    if not recorded:
        logger.info(
            "duplicate scrape completion; checking processing claim",
            extra={"forecast_run_id": run_id, "spot_id": spot_id},
        )

    if not store.claim_processing(forecast_run_id=run_id, spot_id=spot_id):
        store.update_run_rollup(run_id)
        return "processing_already_claimed" if recorded else "duplicate"

    failure_source = "processor"
    try:
        raw_key = message["raw_key"]
        failure_source = "s3"
        envelope = _get_json(message["raw_bucket"], raw_key)
        failure_source = "transform"
        rows = transform_forecast_envelope(envelope, source_raw_key=raw_key)
        failure_source = "postgres"
        if connection is None:
            with connect() as conn:
                insert_forecast_rows(conn, rows)
        else:
            insert_forecast_rows(connection, rows)
    except Exception as exc:
        reason = str(exc)[:1000]
        logger.warning(
            "forecast spot processing failed",
            extra={
                "forecast_run_id": run_id,
                "spot_id": spot_id,
                "failure_source": failure_source,
                "failure_reason": reason,
            },
        )
        store.mark_processing_terminal(
            forecast_run_id=run_id,
            spot_id=spot_id,
            processing_status="failed",
            failure_source=failure_source,
            failure_reason=reason,
        )
        store.update_run_rollup(run_id)
        return "processing_failed"

    store.mark_processing_terminal(
        forecast_run_id=run_id,
        spot_id=spot_id,
        processing_status="success",
    )
    store.update_run_rollup(run_id)
    return "success"


def lambda_handler(event, context):
    store = _store()
    return {
        "results": [
            process_completion(json.loads(record["body"]), store=store)
            for record in event["Records"]
        ]
    }
