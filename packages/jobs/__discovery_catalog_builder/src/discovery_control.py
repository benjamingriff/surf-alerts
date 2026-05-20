import os
from datetime import datetime, timedelta, timezone
from math import ceil
from typing import Any

import boto3
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

DISCOVERY_CONTROL_TABLE_NAME = "DISCOVERY_CONTROL_TABLE_NAME"
RUN_STATUS_PLANNED = "planned"
RUN_STATUS_WAITING_FOR_SPOT_SCRAPES = "waiting_for_spot_scrapes"
RUN_STATUS_SPOT_SCRAPES_COMPLETE = "spot_scrapes_complete"
RUN_STATUS_SPOT_PROCESSING_QUEUED = "spot_processing_queued"
RUN_STATUS_SPOT_PROCESSING = "spot_processing"
RUN_STATUS_COMPLETE = "complete"
RUN_STATUS_NO_OP_COMPLETE = "no_op_complete"
RUN_STATUS_PROCESSING_FAILED = "processing_failed"
SPOT_STATUS_SUCCESS = "success"
SPOT_STATUS_FAILED = "failed"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _isoformat(value: datetime | None = None) -> str:
    return (value or _utc_now()).isoformat()


class ControlStore:
    def __init__(self, table_name: str | None = None, dynamodb_resource=None, ttl_days: int = 14):
        self.table_name = table_name or os.environ.get(DISCOVERY_CONTROL_TABLE_NAME, "discovery-control")
        self.dynamodb = dynamodb_resource or boto3.resource("dynamodb")
        self.table = self.dynamodb.Table(self.table_name)
        self.ttl_days = ttl_days

    def _ttl(self) -> int:
        return ceil((_utc_now() + timedelta(days=self.ttl_days)).timestamp())

    @staticmethod
    def run_key(discovery_run_id: str) -> dict[str, str]:
        return {"pk": f"RUN#{discovery_run_id}", "sk": "RUN"}

    @staticmethod
    def spot_key(discovery_run_id: str, spot_id: str) -> dict[str, str]:
        return {"pk": f"RUN#{discovery_run_id}", "sk": f"SPOT#{spot_id}"}

    def create_run_if_absent(self, *, discovery_run_id: str, scrape_date: str, sitemap_raw_key: str) -> bool:
        try:
            self.table.put_item(
                Item={**self.run_key(discovery_run_id), "item_type": "run", "discovery_run_id": discovery_run_id, "scrape_date": scrape_date, "sitemap_raw_key": sitemap_raw_key, "status": RUN_STATUS_PLANNED, "expected_spot_count": 0, "terminal_scrape_count": 0, "success_scrape_count": 0, "failed_scrape_count": 0, "created_at": _isoformat(), "updated_at": _isoformat(), "expires_at": self._ttl()},
                ConditionExpression="attribute_not_exists(pk)",
            )
            return True
        except ClientError as error:
            if error.response["Error"]["Code"] == "ConditionalCheckFailedException":
                return False
            raise

    def seed_run(self, *, discovery_run_id: str, scrape_date: str, sitemap_raw_key: str, expected_spot_count: int, removed_spot_ids: list[str] | None = None) -> None:
        self.create_run_if_absent(discovery_run_id=discovery_run_id, scrape_date=scrape_date, sitemap_raw_key=sitemap_raw_key)
        self.update_run_plan(discovery_run_id=discovery_run_id, planner_manifest_key="", expected_spot_count=expected_spot_count, added_count=expected_spot_count, removed_count=len(removed_spot_ids or []), existing_spot_count=0, status=RUN_STATUS_WAITING_FOR_SPOT_SCRAPES)

    def update_run_plan(self, *, discovery_run_id: str, planner_manifest_key: str, expected_spot_count: int, added_count: int, removed_count: int, existing_spot_count: int, status: str) -> None:
        self.table.update_item(
            Key=self.run_key(discovery_run_id),
            UpdateExpression="SET planner_manifest_key=:m, expected_spot_count=:e, added_count=:a, removed_count=:r, existing_spot_count=:x, #s=:s, updated_at=:u, expires_at=:ttl",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={":m": planner_manifest_key, ":e": expected_spot_count, ":a": added_count, ":r": removed_count, ":x": existing_spot_count, ":s": status, ":u": _isoformat(), ":ttl": self._ttl()},
        )

    def seed_spots(self, *, discovery_run_id: str, spot_ids: list[str]) -> None:
        with self.table.batch_writer() as batch:
            for spot_id in spot_ids:
                batch.put_item(Item={**self.spot_key(discovery_run_id, spot_id), "item_type": "planned_spot", "discovery_run_id": discovery_run_id, "spot_id": spot_id, "created_at": _isoformat(), "updated_at": _isoformat(), "expires_at": self._ttl()})

    def get_run(self, discovery_run_id: str) -> dict[str, Any] | None:
        return self.table.get_item(Key=self.run_key(discovery_run_id)).get("Item")

    def mark_spot_terminal(self, *, discovery_run_id: str, spot_id: str, terminal_status: str, completed_at: str, raw_key: str | None = None, raw_bucket: str | None = None, failure_reason: str | None = None, failure_source: str | None = None) -> bool:
        values = {":st": terminal_status, ":ts": completed_at, ":u": _isoformat(), ":ttl": self._ttl()}
        sets = ["terminal_status=:st", "completed_at=:ts", "updated_at=:u", "expires_at=:ttl"]
        for name, value in {"raw_key": raw_key, "raw_bucket": raw_bucket, "failure_reason": failure_reason, "failure_source": failure_source}.items():
            if value is not None:
                values[f":{name}"] = value
                sets.append(f"{name}=:{name}")
        try:
            self.table.update_item(Key=self.spot_key(discovery_run_id, spot_id), UpdateExpression="SET " + ", ".join(sets), ConditionExpression="attribute_exists(pk) AND attribute_not_exists(terminal_status)", ExpressionAttributeValues=values)
        except ClientError as error:
            if error.response["Error"]["Code"] == "ConditionalCheckFailedException":
                return False
            raise
        self.table.update_item(Key=self.run_key(discovery_run_id), UpdateExpression="ADD terminal_scrape_count :one, terminal_count :one, success_scrape_count :s, success_count :s, failed_scrape_count :f, failed_count :f SET updated_at=:u, expires_at=:ttl", ExpressionAttributeValues={":one": 1, ":s": 1 if terminal_status == SPOT_STATUS_SUCCESS else 0, ":f": 1 if terminal_status == SPOT_STATUS_FAILED else 0, ":u": _isoformat(), ":ttl": self._ttl()})
        return True

    def transition_run_status(self, *, discovery_run_id: str, from_status: str, to_status: str, extra_attributes: dict[str, Any] | None = None) -> bool:
        names = {"#s": "status"}
        values = {":from": from_status, ":to": to_status, ":u": _isoformat(), ":ttl": self._ttl()}
        sets = ["#s=:to", "updated_at=:u", "expires_at=:ttl"]
        for key, value in (extra_attributes or {}).items():
            names[f"#{key}"] = key; values[f":{key}"] = value; sets.append(f"#{key}=:{key}")
        try:
            self.table.update_item(Key=self.run_key(discovery_run_id), UpdateExpression="SET " + ", ".join(sets), ConditionExpression="#s=:from", ExpressionAttributeNames=names, ExpressionAttributeValues=values)
            return True
        except ClientError as error:
            if error.response["Error"]["Code"] == "ConditionalCheckFailedException":
                return False
            raise

    def list_spots(self, discovery_run_id: str, terminal_status: str | None = None) -> list[dict[str, Any]]:
        items = self.table.query(KeyConditionExpression=Key("pk").eq(f"RUN#{discovery_run_id}") & Key("sk").begins_with("SPOT#")).get("Items", [])
        if terminal_status:
            items = [i for i in items if i.get("terminal_status") == terminal_status]
        return sorted(items, key=lambda i: i["spot_id"])

    def mark_complete(self, discovery_run_id: str) -> None:
        self.table.update_item(Key=self.run_key(discovery_run_id), UpdateExpression="SET #s=:s, completed_at=:c, updated_at=:u, expires_at=:ttl", ExpressionAttributeNames={"#s": "status"}, ExpressionAttributeValues={":s": RUN_STATUS_COMPLETE, ":c": _isoformat(), ":u": _isoformat(), ":ttl": self._ttl()})
