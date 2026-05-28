import os
from datetime import datetime, timedelta, timezone
from math import ceil
from typing import Any

import boto3
from botocore.exceptions import ClientError

from forecast_control.logger import get_logger

FORECAST_CONTROL_TABLE_NAME = "FORECAST_CONTROL_TABLE_NAME"
RUN_STATUS_PLANNED = "planned"
RUN_STATUS_IN_PROGRESS = "in_progress"
RUN_STATUS_COMPLETE = "complete"
SCHEMA_VERSION = 1
PROCESSING_CLAIM_SECONDS = 360
logger = get_logger()


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _isoformat(value: datetime | None = None) -> str:
    return (value or _utc_now()).isoformat()


class ForecastControlStore:
    def __init__(self, table_name: str | None = None, dynamodb_resource=None, ttl_days: int = 7):
        self.table_name = table_name or os.environ.get(
            FORECAST_CONTROL_TABLE_NAME, "forecast-control"
        )
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

    def create_run_if_absent(
        self,
        *,
        forecast_run_id: str,
        scrape_date: str,
        scheduled_utc_time: str,
        local_scrape_time: str,
        local_date: str,
        utc_offset: int,
        expected_scrape_count: int,
    ) -> bool:
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
                        Item=self._spot_item(
                            forecast_run_id=forecast_run_id, spot=spot, now=now, ttl=ttl
                        )
                    )
            return

        for spot in spots:
            try:
                self.table.put_item(
                    Item=self._spot_item(
                        forecast_run_id=forecast_run_id, spot=spot, now=now, ttl=ttl
                    ),
                    ConditionExpression="attribute_not_exists(pk)",
                )
            except ClientError as error:
                if error.response["Error"]["Code"] == "ConditionalCheckFailedException":
                    continue
                raise

    def get_run(
        self, forecast_run_id: str, *, consistent_read: bool = False
    ) -> dict[str, Any] | None:
        return self.table.get_item(
            Key=self.run_key(forecast_run_id), ConsistentRead=consistent_read
        ).get("Item")

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

    def record_scrape_terminal(
        self,
        *,
        forecast_run_id: str,
        spot_id: str,
        scrape_status: str,
        raw_bucket: str | None = None,
        raw_key: str | None = None,
        scraped_at: str | None = None,
        failure_source: str | None = None,
        failure_reason: str | None = None,
    ) -> bool:
        is_success = scrape_status == "success"
        status = "success" if is_success else "failed"
        update = [
            "SET scrape_status=:status",
            "scrape_completed_at=:now",
            "updated_at=:now",
            "expires_at=:ttl",
        ]
        values: dict[str, Any] = {
            ":status": status,
            ":now": _isoformat(),
            ":ttl": self._ttl(),
            ":planned": "planned",
            ":in_progress": "in_progress",
        }
        if raw_bucket is not None:
            update.append("raw_bucket=:raw_bucket")
            values[":raw_bucket"] = raw_bucket
        if raw_key is not None:
            update.append("raw_key=:raw_key")
            values[":raw_key"] = raw_key
        if scraped_at is not None:
            update.append("scraped_at=:scraped_at")
            values[":scraped_at"] = scraped_at
        if failure_source is not None:
            update.append("scrape_failure_source=:failure_source")
            values[":failure_source"] = failure_source
        if failure_reason is not None:
            update.append("scrape_failure_reason=:failure_reason")
            values[":failure_reason"] = failure_reason
        run_inc = "successful_scrape_count" if is_success else "failed_scrape_count"
        run_adds = ["terminal_scrape_count :one", f"{run_inc} :one"]
        if is_success:
            run_adds.append("expected_processing_count :one")
        run_update_expression = "SET updated_at=:now, expires_at=:ttl ADD " + ", ".join(run_adds)
        try:
            self.table.update_item(
                Key=self.spot_key(forecast_run_id, spot_id),
                UpdateExpression=", ".join(update),
                ExpressionAttributeValues=values,
                ConditionExpression="scrape_status IN (:planned, :in_progress)",
            )
        except ClientError as error:
            if error.response["Error"]["Code"] == "ConditionalCheckFailedException":
                return False
            raise

        logger.info(
            "forecast scrape terminal run counter update",
            extra={
                "forecast_run_id": forecast_run_id,
                "spot_id": spot_id,
                "scrape_status": status,
                "run_update_expression": run_update_expression,
            },
        )
        self.table.update_item(
            Key=self.run_key(forecast_run_id),
            UpdateExpression=run_update_expression,
            ExpressionAttributeValues={
                ":one": 1,
                ":now": _isoformat(),
                ":ttl": self._ttl(),
            },
        )
        return True

    def claim_processing(self, *, forecast_run_id: str, spot_id: str) -> bool:
        now = _utc_now()
        stale_before = (now - timedelta(seconds=PROCESSING_CLAIM_SECONDS)).isoformat()
        try:
            self.table.update_item(
                Key=self.spot_key(forecast_run_id, spot_id),
                UpdateExpression="SET processing_status=:in_progress, processing_claimed_at=:now, updated_at=:now, expires_at=:ttl",
                ExpressionAttributeValues={
                    ":in_progress": "in_progress",
                    ":not_started": "not_started",
                    ":stale_before": stale_before,
                    ":now": now.isoformat(),
                    ":ttl": self._ttl(),
                },
                ConditionExpression="processing_status=:not_started OR (processing_status=:in_progress AND processing_claimed_at < :stale_before)",
            )
            return True
        except ClientError as error:
            if error.response["Error"]["Code"] == "ConditionalCheckFailedException":
                return False
            raise

    def mark_processing_terminal(
        self,
        *,
        forecast_run_id: str,
        spot_id: str,
        processing_status: str,
        failure_source: str | None = None,
        failure_reason: str | None = None,
    ) -> bool:
        is_success = processing_status == "success"
        status = "success" if is_success else "failed"
        update = [
            "SET processing_status=:status",
            "processing_completed_at=:now",
            "updated_at=:now",
            "expires_at=:ttl",
        ]
        values: dict[str, Any] = {
            ":status": status,
            ":in_progress": "in_progress",
            ":now": _isoformat(),
            ":ttl": self._ttl(),
        }
        if failure_source is not None:
            update.append("processing_failure_source=:failure_source")
            values[":failure_source"] = failure_source
        if failure_reason is not None:
            update.append("processing_failure_reason=:failure_reason")
            values[":failure_reason"] = failure_reason
        run_inc = "successful_processing_count" if is_success else "failed_processing_count"
        try:
            self.table.update_item(
                Key=self.spot_key(forecast_run_id, spot_id),
                UpdateExpression=", ".join(update),
                ExpressionAttributeValues=values,
                ConditionExpression="processing_status=:in_progress",
            )
        except ClientError as error:
            if error.response["Error"]["Code"] == "ConditionalCheckFailedException":
                return False
            raise

        self.table.update_item(
            Key=self.run_key(forecast_run_id),
            UpdateExpression=(
                "SET updated_at=:now, expires_at=:ttl ADD "
                f"terminal_processing_count :one, {run_inc} :one"
            ),
            ExpressionAttributeValues={
                ":one": 1,
                ":now": _isoformat(),
                ":ttl": self._ttl(),
            },
        )
        return True

    def update_run_rollup(self, forecast_run_id: str) -> None:
        run = self.get_run(forecast_run_id, consistent_read=True)
        if not run:
            return
        expected_scrapes = run.get("expected_scrape_count", 0)
        terminal_scrapes = run.get("terminal_scrape_count", 0)
        expected_processing = run.get("expected_processing_count", 0)
        terminal_processing = run.get("terminal_processing_count", 0)
        scrape_complete = terminal_scrapes >= expected_scrapes
        processing_complete = terminal_processing >= expected_processing

        scrape_status = "in_progress"
        if scrape_complete:
            scrape_status = (
                "complete_with_failures" if run.get("failed_scrape_count", 0) else "complete"
            )

        processing_status = "not_started"
        if expected_processing > 0 and not processing_complete:
            processing_status = "in_progress"
        elif processing_complete:
            processing_status = (
                "complete_with_failures" if run.get("failed_processing_count", 0) else "complete"
            )

        update = "SET updated_at=:now, expires_at=:ttl, scrape_status=:scrape_status, processing_status=:processing_status"
        values: dict[str, Any] = {
            ":now": _isoformat(),
            ":ttl": self._ttl(),
            ":scrape_status": scrape_status,
            ":processing_status": processing_status,
        }
        kwargs = {
            "Key": self.run_key(forecast_run_id),
            "UpdateExpression": update,
            "ExpressionAttributeValues": values,
        }
        if scrape_complete and processing_complete:
            kwargs["UpdateExpression"] += ", #s=:complete"
            kwargs["ExpressionAttributeNames"] = {"#s": "status"}
            values[":complete"] = RUN_STATUS_COMPLETE
        self.table.update_item(**kwargs)
