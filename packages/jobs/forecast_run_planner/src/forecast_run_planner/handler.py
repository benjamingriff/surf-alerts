import json
import os
import re
from datetime import datetime, timedelta
from typing import Any

import boto3
from forecast_control import ForecastControlStore
from postgres_client import connect

SCHEMA_VERSION = 1


def _sqs():
    return boto3.client("sqs")


def _store() -> ForecastControlStore:
    return ForecastControlStore()


def parse_scheduled_time(value: str) -> datetime:
    scheduled = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if scheduled.tzinfo is None or scheduled.utcoffset() != timedelta(0):
        raise ValueError("EventBridge time must be UTC")
    return scheduled


def parse_local_scrape_time(value: str) -> tuple[int, int]:
    if not re.fullmatch(r"\d{2}:00", value):
        raise ValueError("FORECAST_SCRAPE_LOCAL_TIME must be HH:00 for v1")
    hour = int(value[:2])
    if not 0 <= hour <= 23:
        raise ValueError("FORECAST_SCRAPE_LOCAL_TIME must be HH:00 for v1")
    return hour, 0


def due_utc_offsets(
    *, scheduled_utc_time: datetime, local_scrape_time: str, min_offset: int, max_offset: int
) -> list[int]:
    local_hour, _ = parse_local_scrape_time(local_scrape_time)
    scheduled_hour = scheduled_utc_time.hour
    return [
        offset
        for offset in range(min_offset, max_offset + 1)
        if (scheduled_hour + offset) % 24 == local_hour
    ]


def forecast_run_id(*, utc_offset: int, scrape_date: str, local_scrape_time: str) -> str:
    return f"forecast#offset={utc_offset}#scrape_date={scrape_date}#time={local_scrape_time.replace(':', '-')}"


def _live_spots_for_offset(utc_offset: int) -> list[dict[str, Any]]:
    with connect(os.environ["SUPABASE_POSTGRES_URL_PARAMETER_NAME"]) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                select spot_id, spot_version_id, name, utc_offset, timezone, lat as latitude, lon as longitude
                from discovery_spot_versions
                where is_current = true
                  and event_type <> 'removed'
                  and utc_offset = %s
                order by spot_id
                """,
                (utc_offset,),
            )
            return list(cur.fetchall())


def _chunks(items: list[dict[str, Any]], size: int):
    for start in range(0, len(items), size):
        yield items[start : start + size]


def _queue_scrapes(
    *,
    queue_url: str,
    forecast_run_id: str,
    scheduled_utc_time: str,
    scrape_date: str,
    local_date: str,
    local_scrape_time: str,
    spots: list[dict[str, Any]],
) -> None:
    sqs = _sqs()
    for chunk in _chunks(spots, 10):
        response = sqs.send_message_batch(
            QueueUrl=queue_url,
            Entries=[
                {
                    "Id": str(index),
                    "MessageBody": json.dumps(
                        {
                            "schema_version": SCHEMA_VERSION,
                            "message_type": "forecast_spot_scrape_requested",
                            "forecast_run_id": forecast_run_id,
                            "scheduled_utc_time": scheduled_utc_time,
                            "scrape_date": scrape_date,
                            "local_date": local_date,
                            "local_scrape_time": local_scrape_time,
                            "spot_id": spot["spot_id"],
                            "spot_version_id": spot.get("spot_version_id"),
                            "spot_name": spot.get("name"),
                            "utc_offset": spot.get("utc_offset"),
                            "timezone": spot.get("timezone"),
                            "latitude": spot.get("latitude"),
                            "longitude": spot.get("longitude"),
                        }
                    ),
                }
                for index, spot in enumerate(chunk)
            ],
        )
        if response.get("Failed"):
            raise RuntimeError(f"Failed to queue forecast scrape messages: {response['Failed']}")


def plan_forecast_run_for_offset(
    *, scheduled: datetime, local_scrape_time: str, utc_offset: int, store: ForecastControlStore
) -> dict[str, Any]:
    spots = _live_spots_for_offset(utc_offset)
    if not spots:
        return {"utc_offset": utc_offset, "result": "empty_offset"}

    scrape_date = scheduled.date().isoformat()
    local_date = (scheduled + timedelta(hours=utc_offset)).date().isoformat()
    run_id = forecast_run_id(
        utc_offset=utc_offset, scrape_date=scrape_date, local_scrape_time=local_scrape_time
    )
    scheduled_iso = scheduled.isoformat()
    created = store.create_run_if_absent(
        forecast_run_id=run_id,
        scrape_date=scrape_date,
        scheduled_utc_time=scheduled_iso,
        local_scrape_time=local_scrape_time,
        local_date=local_date,
        utc_offset=utc_offset,
        expected_scrape_count=len(spots),
    )
    if not created:
        existing_run = store.get_run(run_id)
        if existing_run is None or existing_run.get("status") != "planned":
            return {"utc_offset": utc_offset, "forecast_run_id": run_id, "result": "duplicate"}

    store.seed_spots(forecast_run_id=run_id, spots=spots, overwrite_existing=created)
    _queue_scrapes(
        queue_url=os.environ["FORECAST_SCRAPER_QUEUE_URL"],
        forecast_run_id=run_id,
        scheduled_utc_time=scheduled_iso,
        scrape_date=scrape_date,
        local_date=local_date,
        local_scrape_time=local_scrape_time,
        spots=spots,
    )
    store.mark_run_in_progress(run_id)
    return {
        "utc_offset": utc_offset,
        "forecast_run_id": run_id,
        "result": "planned" if created else "retried_planned",
    }


def plan_forecast_runs(event: dict[str, Any]) -> list[dict[str, Any]]:
    local_scrape_time = os.environ.get("FORECAST_SCRAPE_LOCAL_TIME", "04:00")
    min_offset = int(os.environ.get("FORECAST_MIN_UTC_OFFSET", "-12"))
    max_offset = int(os.environ.get("FORECAST_MAX_UTC_OFFSET", "14"))
    scheduled = parse_scheduled_time(event["time"])
    offsets = due_utc_offsets(
        scheduled_utc_time=scheduled,
        local_scrape_time=local_scrape_time,
        min_offset=min_offset,
        max_offset=max_offset,
    )
    if not offsets:
        return [{"result": "no_due_offset"}]

    store = _store()
    return [
        plan_forecast_run_for_offset(
            scheduled=scheduled,
            local_scrape_time=local_scrape_time,
            utc_offset=offset,
            store=store,
        )
        for offset in offsets
    ]


def lambda_handler(event, context):
    return {"statusCode": 200, "body": json.dumps({"results": plan_forecast_runs(event)})}
