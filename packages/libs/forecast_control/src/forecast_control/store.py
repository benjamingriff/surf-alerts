import os
from datetime import datetime, timedelta, timezone
from math import ceil
from typing import Any

import boto3
from botocore.exceptions import ClientError

FORECAST_CONTROL_TABLE_NAME = "FORECAST_CONTROL_TABLE_NAME"
RUN_STATUS_PLANNED = "planned"
RUN_STATUS_IN_PROGRESS = "in_progress"
SCHEMA_VERSION = 1


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _isoformat(value: datetime | None = None) -> str:
    return (value or _utc_now()).isoformat()


class ForecastControlStore:
    def __init__(self, table_name: str | None = None, dynamodb_resource=None, ttl_days: int = 7):
        self.table_name = table_name or os.environ.get(FORECAST_CONTROL_TABLE_NAME, "forecast-control")
        self.dynamodb = dynamodb_resource or boto3.resource("dynamodb")
        self.table = self.dynamodb.Table(self.table_name)
        self.ttl_days = ttl_days

    def _ttl(self) -> int:
        return ceil((_utc_now() + timedelta(days=self.ttl_days)).timestamp())

    @staticmethod
    def run_key(forecast_run_id: str) -> dict[str, str]:
        return {"pk": f"FORECAST_RUN#{forecast_run_id}", "sk": "RUN"}

    @staticmethod
    def spot_key(forecast_run_id: str, spot_id: str) -> dict[str, str]:
        return {"pk": f"FORECAST_RUN#{forecast_run_id}", "sk": f"SPOT#{spot_id}"}

    def create_run_if_absent(self, *, forecast_run_id: str, scrape_date: str, scheduled_utc_time: str, local_scrape_time: str, local_date: str, utc_offset: int, expected_scrape_count: int) -> bool:
        now = _isoformat()
        try:
            self.table.put_item(
                Item={
                    **self.run_key(forecast_run_id),
                    "item_type": "forecast_run",
                    "schema_version": SCHEMA_VERSION,
                    "forecast_run_id": forecast_run_id,
                    "scrape_date": scrape_date,
                    "scheduled_utc_time": scheduled_utc_time,
                    "local_scrape_time": local_scrape_time,
                    "local_date": local_date,
                    "utc_offset": utc_offset,
                    "status": RUN_STATUS_PLANNED,
                    "scrape_status": "in_progress",
                    "processing_status": "not_started",
                    "expected_scrape_count": expected_scrape_count,
                    "terminal_scrape_count": 0,
                    "successful_scrape_count": 0,
                    "failed_scrape_count": 0,
                    "expected_processing_count": 0,
                    "terminal_processing_count": 0,
                    "successful_processing_count": 0,
                    "failed_processing_count": 0,
                    "created_at": now,
                    "updated_at": now,
                    "expires_at": self._ttl(),
                },
                ConditionExpression="attribute_not_exists(pk)",
            )
            return True
        except ClientError as error:
            if error.response["Error"]["Code"] == "ConditionalCheckFailedException":
                return False
            raise

    def _spot_item(
        self, *, forecast_run_id: str, spot: dict[str, Any], now: str, ttl: int
    ) -> dict[str, Any]:
        return {
            **self.spot_key(forecast_run_id, spot["spot_id"]),
            "item_type": "forecast_planned_spot",
            "forecast_run_id": forecast_run_id,
            "spot_id": spot["spot_id"],
            "spot_version_id": spot.get("spot_version_id"),
            "scrape_status": "planned",
            "processing_status": "not_started",
            "created_at": now,
            "updated_at": now,
            "expires_at": ttl,
        }

    def seed_spots(
        self, *, forecast_run_id: str, spots: list[dict[str, Any]], overwrite_existing: bool = True
    ) -> None:
        now = _isoformat()
        ttl = self._ttl()
        if overwrite_existing:
            with self.table.batch_writer(overwrite_by_pkeys=["pk", "sk"]) as batch:
                for spot in spots:
                    batch.put_item(
                        Item=self._spot_item(forecast_run_id=forecast_run_id, spot=spot, now=now, ttl=ttl)
                    )
            return

        for spot in spots:
            try:
                self.table.put_item(
                    Item=self._spot_item(forecast_run_id=forecast_run_id, spot=spot, now=now, ttl=ttl),
                    ConditionExpression="attribute_not_exists(pk)",
                )
            except ClientError as error:
                if error.response["Error"]["Code"] == "ConditionalCheckFailedException":
                    continue
                raise

    def get_run(self, forecast_run_id: str) -> dict[str, Any] | None:
        return self.table.get_item(Key=self.run_key(forecast_run_id)).get("Item")

    def mark_run_in_progress(self, forecast_run_id: str) -> bool:
        try:
            self.table.update_item(
                Key=self.run_key(forecast_run_id),
                UpdateExpression="SET #s=:s, updated_at=:u, expires_at=:ttl",
                ExpressionAttributeNames={"#s": "status"},
                ExpressionAttributeValues={
                    ":s": RUN_STATUS_IN_PROGRESS,
                    ":planned": RUN_STATUS_PLANNED,
                    ":u": _isoformat(),
                    ":ttl": self._ttl(),
                },
                ConditionExpression="#s=:planned",
            )
            return True
        except ClientError as error:
            if error.response["Error"]["Code"] == "ConditionalCheckFailedException":
                return False
            raise
