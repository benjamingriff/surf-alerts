import gzip
import json
from contextlib import contextmanager

import boto3
from moto import mock_aws

from forecast_spot_processor.handler import process_completion


def envelope():
    ts = 1_700_000_000
    return {
        "schema_version": 1,
        "forecast_run_id": "run-1",
        "spot_id": "spot-1",
        "spot_version_id": "version-1",
        "scraped_at": "2026-05-22T14:01:00+00:00",
        "scheduled_utc_time": "2026-05-22T14:00:00+00:00",
        "utc_offset": -10,
        "timezone": "Pacific/Honolulu",
        "raw_payload": {
            "rating": {
                "data": {"rating": [{"timestamp": ts, "rating": {"key": "GOOD", "value": 1}}]}
            },
            "wave": {
                "data": {
                    "wave": [
                        {
                            "timestamp": ts,
                            "surf": {"min": 1, "max": 2},
                            "swells": [{"height": 0}, {"height": 1}],
                        }
                    ]
                }
            },
            "wind": {"data": {"wind": [{"timestamp": ts, "speed": 4}]}},
            "tides": {"data": {"tides": [{"timestamp": ts, "type": "NORMAL", "height": 2.1}]}},
        },
    }


class StoreSpy:
    def __init__(self):
        self.calls = []
        self.record_result = True
        self.claim_result = True

    def record_scrape_terminal(self, **kwargs):
        self.calls.append(("record_scrape_terminal", kwargs))
        return self.record_result

    def claim_processing(self, **kwargs):
        self.calls.append(("claim_processing", kwargs))
        return self.claim_result

    def mark_processing_terminal(self, **kwargs):
        self.calls.append(("mark_processing_terminal", kwargs))

    def update_run_rollup(self, run_id):
        self.calls.append(("update_run_rollup", run_id))


class CursorSpy:
    def __init__(self):
        self.executed = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def executemany(self, sql, values):
        self.executed.append((sql, values))


class ConnSpy:
    def __init__(self):
        self.cursor_spy = CursorSpy()
        self.transactions = 0

    @contextmanager
    def transaction(self):
        self.transactions += 1
        yield

    def cursor(self):
        return self.cursor_spy


@mock_aws
def test_success_completion_uses_reusable_connection_when_not_injected(monkeypatch):
    s3 = boto3.client("s3", region_name="us-east-1")
    s3.create_bucket(Bucket="raw-bucket")
    body = gzip.compress(json.dumps(envelope()).encode())
    s3.put_object(Bucket="raw-bucket", Key="forecast/raw.json.gz", Body=body)
    store = StoreSpy()
    conn = ConnSpy()
    monkeypatch.setattr(
        "forecast_spot_processor.handler.get_reusable_connection", lambda: conn
    )

    result = process_completion(
        {
            "forecast_run_id": "run-1",
            "spot_id": "spot-1",
            "scrape_status": "success",
            "raw_bucket": "raw-bucket",
            "raw_key": "forecast/raw.json.gz",
            "scraped_at": "2026-05-22T14:01:00+00:00",
        },
        store=store,
    )

    assert result == "success"
    assert conn.transactions == 1


@mock_aws
def test_success_completion_reads_raw_transforms_inserts_all_tables_and_marks_success():
    s3 = boto3.client("s3", region_name="us-east-1")
    s3.create_bucket(Bucket="raw-bucket")
    body = gzip.compress(json.dumps(envelope()).encode())
    s3.put_object(Bucket="raw-bucket", Key="forecast/raw.json.gz", Body=body)
    store = StoreSpy()
    conn = ConnSpy()

    result = process_completion(
        {
            "forecast_run_id": "run-1",
            "spot_id": "spot-1",
            "scrape_status": "success",
            "raw_bucket": "raw-bucket",
            "raw_key": "forecast/raw.json.gz",
            "scraped_at": "2026-05-22T14:01:00+00:00",
        },
        store=store,
        connection=conn,
    )

    assert result == "success"
    assert conn.transactions == 1
    assert len(conn.cursor_spy.executed) == 5
    assert all(
        " on conflict (" in sql and " do nothing" in sql for sql, _ in conn.cursor_spy.executed
    )
    assert [name for name, _ in store.calls] == [
        "record_scrape_terminal",
        "claim_processing",
        "mark_processing_terminal",
        "update_run_rollup",
    ]
    assert store.calls[2][1]["processing_status"] == "success"


@mock_aws
def test_processing_failure_marks_terminal_and_does_not_raise():
    store = StoreSpy()
    conn = ConnSpy()

    result = process_completion(
        {
            "forecast_run_id": "run-1",
            "spot_id": "spot-1",
            "scrape_status": "success",
            "raw_bucket": "missing-bucket",
            "raw_key": "missing-key.json.gz",
        },
        store=store,
        connection=conn,
    )

    assert result == "processing_failed"
    assert [name for name, _ in store.calls] == [
        "record_scrape_terminal",
        "claim_processing",
        "mark_processing_terminal",
        "update_run_rollup",
    ]
    failure = store.calls[2][1]
    assert failure["processing_status"] == "failed"
    assert failure["failure_source"] == "s3"
    assert failure["failure_reason"]


def test_duplicate_success_completion_without_claim_skips_writes():
    store = StoreSpy()
    store.record_result = False
    store.claim_result = False
    conn = ConnSpy()

    result = process_completion(
        {"forecast_run_id": "run-1", "spot_id": "spot-1", "scrape_status": "success"},
        store=store,
        connection=conn,
    )

    assert result == "duplicate"
    assert [name for name, _ in store.calls] == [
        "record_scrape_terminal",
        "claim_processing",
        "update_run_rollup",
    ]
    assert conn.cursor_spy.executed == []


def test_failed_scrape_completion_records_failure_and_skips_processing():
    store = StoreSpy()
    conn = ConnSpy()

    result = process_completion(
        {
            "forecast_run_id": "run-1",
            "spot_id": "spot-1",
            "scrape_status": "failed",
            "failure_source": "fetch",
            "failure_reason": "timeout",
        },
        store=store,
        connection=conn,
    )

    assert result == "scrape_failed"
    assert [name for name, _ in store.calls] == ["record_scrape_terminal", "update_run_rollup"]
    assert store.calls[0][1]["failure_source"] == "fetch"
    assert conn.cursor_spy.executed == []


@mock_aws
def test_duplicate_success_completion_can_reclaim_processing_and_insert_rows():
    s3 = boto3.client("s3", region_name="us-east-1")
    s3.create_bucket(Bucket="raw-bucket")
    body = gzip.compress(json.dumps(envelope()).encode())
    s3.put_object(Bucket="raw-bucket", Key="forecast/raw.json.gz", Body=body)
    store = StoreSpy()
    store.record_result = False
    conn = ConnSpy()

    result = process_completion(
        {
            "forecast_run_id": "run-1",
            "spot_id": "spot-1",
            "scrape_status": "success",
            "raw_bucket": "raw-bucket",
            "raw_key": "forecast/raw.json.gz",
        },
        store=store,
        connection=conn,
    )

    assert result == "success"
    assert conn.transactions == 1
    assert [name for name, _ in store.calls] == [
        "record_scrape_terminal",
        "claim_processing",
        "mark_processing_terminal",
        "update_run_rollup",
    ]
