import gzip
import json
import os

import boto3

from discovery_control import ControlStore
from discovery_spot_batch_processor.handler import lambda_handler


class InMemoryCursor:
    def __init__(self, db):
        self.db = db
        self.result_all = []
        self.result_one = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, sql, params=None):
        if "spot_id = any" in sql:
            ids = set(params[0])
            self.result_all = [
                r.copy()
                for r in self.db
                if r.get("is_current") is True
                and r.get("event_type") != "removed"
                and r["spot_id"] in ids
            ]
        elif sql.startswith("update discovery_spot_versions set is_current=false"):
            valid_to, spot_id = params
            for row in self.db:
                if row["spot_id"] == spot_id and row.get("is_current") is True:
                    row["is_current"] = False
                    row["valid_to"] = valid_to
        elif "where spot_id=%s" in sql:
            spot_id = params[0]
            matches = [
                r
                for r in self.db
                if r["spot_id"] == spot_id
                and r.get("is_current") is True
                and r.get("event_type") != "removed"
            ]
            self.result_one = matches[0].copy() if matches else None
        elif sql.startswith("insert into discovery_spot_versions"):
            cols = sql.split("(", 1)[1].split(")", 1)[0].split(",")
            row = dict(zip(cols, params))
            for col in [
                "breadcrumbs",
                "cameras",
                "ability_levels",
                "board_types",
                "travel_details",
            ]:
                if isinstance(row.get(col), str):
                    row[col] = json.loads(row[col])
            if not any(
                existing["spot_version_id"] == row["spot_version_id"] for existing in self.db
            ):
                self.db.append(row)
        else:
            raise AssertionError(f"Unexpected SQL: {sql}")

    def fetchall(self):
        return self.result_all

    def fetchone(self):
        return self.result_one


class InMemoryTransaction:
    def __init__(self, conn):
        self.conn = conn
        self.snapshot = None

    def __enter__(self):
        self.snapshot = [row.copy() for row in self.conn.db]
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc_type is not None:
            self.conn.db[:] = self.snapshot
        return False


class InMemoryConnection:
    def __init__(self, db):
        self.db = db

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def transaction(self):
        return InMemoryTransaction(self)

    def cursor(self):
        return InMemoryCursor(self.db)


def _store():
    return ControlStore(
        table_name=os.environ["DISCOVERY_CONTROL_TABLE_NAME"],
        dynamodb_resource=boto3.resource("dynamodb", region_name="eu-west-2"),
    )


def _put_gzip_json(s3, bucket, key, body):
    s3.put_object(
        Bucket=bucket,
        Key=key,
        Body=gzip.compress(json.dumps(body).encode()),
        ContentEncoding="gzip",
    )


def test_batch_processor_happy_path_adds_successes_removes_tombstones_and_marks_complete(
    s3, monkeypatch, lambda_context
):
    bucket = os.environ["S3_BUCKET_NAME"]
    monkeypatch.setenv("DATA_BUCKET", bucket)
    monkeypatch.setenv("SUPABASE_POSTGRES_URL_PARAMETER_NAME", "/param")
    monkeypatch.setattr(
        "discovery_spot_batch_processor.handler._utc_now_iso", lambda: "2026-05-01T06:10:00Z"
    )
    manifest_key = "control/discovery/planner_manifest/discovery_run_id=run-1.json"
    manifest = {"removed_spot_ids": ["old"], "sitemap_raw_key": "raw/sitemap/x.json.gz"}
    s3.put_object(Bucket=bucket, Key=manifest_key, Body=json.dumps(manifest).encode())
    raw_key = "raw/spot_report/scrape_date=2026-05-01/discovery_run_id=run-1/spot_id=new.json.gz"
    _put_gzip_json(
        s3,
        bucket,
        raw_key,
        {"raw_payload": {"spot": {"name": "New Spot", "location": {"lat": 1, "lon": 2}}}},
    )
    store = _store()
    store.seed_run(
        discovery_run_id="run-1",
        scrape_date="2026-05-01",
        sitemap_raw_key="raw/sitemap/x.json.gz",
        expected_spot_count=1,
    )
    store.update_run_plan(
        discovery_run_id="run-1",
        planner_manifest_key=manifest_key,
        expected_spot_count=1,
        added_count=1,
        removed_count=1,
        existing_spot_count=0,
        status="spot_processing_queued",
    )
    store.seed_spots(discovery_run_id="run-1", spot_ids=["new"])
    store.mark_spot_terminal(
        discovery_run_id="run-1",
        spot_id="new",
        terminal_status="success",
        completed_at="2026-05-01T06:02:00Z",
        raw_bucket=bucket,
        raw_key=raw_key,
    )
    db = [
        {
            "spot_version_id": "old-v",
            "spot_id": "old",
            "event_type": "added",
            "is_current": True,
            "content_checksum": "old-checksum",
            "name": "Old Spot",
        }
    ]
    monkeypatch.setattr(
        "discovery_spot_batch_processor.handler.connect", lambda _: InMemoryConnection(db)
    )

    response = lambda_handler(
        {"Records": [{"body": json.dumps({"discovery_run_id": "run-1"})}]}, lambda_context
    )

    assert response["statusCode"] == 200
    assert json.loads(response["body"]) == {"results": ["processed"]}
    assert store.get_run("run-1")["status"] == "complete"
    old_rows = [r for r in db if r["spot_id"] == "old"]
    assert any(r["event_type"] == "added" and r["is_current"] is False for r in old_rows)
    assert any(
        r["event_type"] == "removed" and r["is_current"] is True and r["name"] == "Old Spot"
        for r in old_rows
    )
    new = [r for r in db if r["spot_id"] == "new"][0]
    assert new["event_type"] == "added"
    assert new["is_current"] is True
    assert new["name"] == "New Spot"
    assert new["source_raw_key"] == raw_key


def test_batch_processor_conflict_rolls_back_and_does_not_mark_complete(
    s3, monkeypatch, lambda_context
):
    bucket = os.environ["S3_BUCKET_NAME"]
    monkeypatch.setenv("DATA_BUCKET", bucket)
    monkeypatch.setenv("SUPABASE_POSTGRES_URL_PARAMETER_NAME", "/param")
    monkeypatch.setattr(
        "discovery_spot_batch_processor.handler._utc_now_iso", lambda: "2026-05-01T06:10:00Z"
    )
    manifest_key = "control/discovery/planner_manifest/discovery_run_id=run-conflict.json"
    s3.put_object(
        Bucket=bucket,
        Key=manifest_key,
        Body=json.dumps(
            {"removed_spot_ids": [], "sitemap_raw_key": "raw/sitemap/x.json.gz"}
        ).encode(),
    )
    raw_key = (
        "raw/spot_report/scrape_date=2026-05-01/discovery_run_id=run-conflict/spot_id=new.json.gz"
    )
    _put_gzip_json(s3, bucket, raw_key, {"raw_payload": {"spot": {"name": "New Spot"}}})
    store = _store()
    store.seed_run(
        discovery_run_id="run-conflict",
        scrape_date="2026-05-01",
        sitemap_raw_key="raw/sitemap/x.json.gz",
        expected_spot_count=1,
    )
    store.update_run_plan(
        discovery_run_id="run-conflict",
        planner_manifest_key=manifest_key,
        expected_spot_count=1,
        added_count=1,
        removed_count=0,
        existing_spot_count=0,
        status="spot_processing_queued",
    )
    store.seed_spots(discovery_run_id="run-conflict", spot_ids=["new"])
    store.mark_spot_terminal(
        discovery_run_id="run-conflict",
        spot_id="new",
        terminal_status="success",
        completed_at="2026-05-01T06:02:00Z",
        raw_bucket=bucket,
        raw_key=raw_key,
    )
    db = [
        {
            "spot_version_id": "different",
            "spot_id": "new",
            "event_type": "added",
            "is_current": True,
            "content_checksum": "old",
            "name": "Existing",
        }
    ]
    monkeypatch.setattr(
        "discovery_spot_batch_processor.handler.connect", lambda _: InMemoryConnection(db)
    )

    try:
        lambda_handler(
            {"Records": [{"body": json.dumps({"discovery_run_id": "run-conflict"})}]},
            lambda_context,
        )
        raise AssertionError("expected conflict")
    except RuntimeError as error:
        assert "Current active spot conflict for new" in str(error)

    assert store.get_run("run-conflict")["status"] == "spot_processing"
    assert db == [
        {
            "spot_version_id": "different",
            "spot_id": "new",
            "event_type": "added",
            "is_current": True,
            "content_checksum": "old",
            "name": "Existing",
        }
    ]
