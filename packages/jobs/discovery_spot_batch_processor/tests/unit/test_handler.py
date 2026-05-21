from contextlib import contextmanager

import pytest

from discovery_spot_model import build_added_spot_version_row, canonicalize_spot_report
from discovery_spot_batch_processor.handler import (
    COLUMNS,
    _s3_read_workers,
    apply_spot_version_changes,
    build_added_row,
    build_added_rows,
    lambda_handler,
    process_discovery_run,
    serialize_row_values,
    should_process_run,
)


def raw_spot(name="A", spot_id="s1"):
    return {
        "raw_payload": {
            "spot": {
                "spot_id": spot_id,
                "name": name,
                "lat": 1,
                "lon": 2,
                "timezone": "Europe/London",
                "utc_offset": 0,
                "abbr_timezone": "GMT",
                "href": f"https://example.com/{spot_id}",
            }
        }
    }


class FakeStore:
    def __init__(self, run=None, spots=None, transition_result=True):
        self.run = run
        self.spots = spots or []
        self.completed = []
        self.transitions = []
        self.transition_result = transition_result

    def get_run(self, run_id):
        return self.run

    def list_spots(self, run_id, terminal_status=None):
        return [
            s
            for s in self.spots
            if terminal_status is None or s.get("terminal_status") == terminal_status
        ]

    def mark_complete(self, run_id):
        self.completed.append(run_id)

    def transition_run_status(
        self, *, discovery_run_id, from_status, to_status, extra_attributes=None
    ):
        self.transitions.append(
            {
                "discovery_run_id": discovery_run_id,
                "from_status": from_status,
                "to_status": to_status,
                "extra_attributes": extra_attributes,
            }
        )
        if self.transition_result and self.run:
            self.run["status"] = to_status
        return self.transition_result


class FakeCursor:
    def __init__(self, *, removed_rows=None, existing_by_spot=None):
        self.removed_rows = removed_rows or []
        self.existing_by_spot = existing_by_spot or {}
        self.executed = []
        self._fetchall = []
        self._fetchone = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, sql, params=None):
        self.executed.append((sql, params))
        if "spot_id = any" in sql:
            ids = set(params[0])
            if "event_type <> 'removed'" in sql:
                self._fetchall = [
                    row for row in self.removed_rows if row["spot_id"] in ids
                ]
            else:
                self._fetchall = [
                    {"spot_id": spot_id, **row}
                    for spot_id, row in self.existing_by_spot.items()
                    if spot_id in ids
                ]
        elif "where spot_id=%s" in sql:
            row = self.existing_by_spot.get(params[0])
            if row and "event_type <> 'removed'" in sql and row.get("event_type") == "removed":
                self._fetchone = None
            else:
                self._fetchone = row

    def executemany(self, sql, params_seq):
        for params in params_seq:
            self.executed.append((sql, params))

    def fetchall(self):
        return self._fetchall

    def fetchone(self):
        return self._fetchone


class FakeTransaction:
    def __init__(self, conn):
        self.conn = conn

    def __enter__(self):
        self.conn.opened = True
        return self

    def __exit__(self, exc_type, exc, tb):
        self.conn.committed = exc_type is None
        self.conn.rolled_back = exc_type is not None
        return False


class FakeConnection:
    def __init__(self, cursor):
        self.cursor_obj = cursor
        self.opened = False
        self.committed = False
        self.rolled_back = False

    def transaction(self):
        return FakeTransaction(self)

    def cursor(self):
        return self.cursor_obj


def test_serialize_row_values_json_encodes_json_columns():
    row = {column: None for column in COLUMNS}
    row.update(
        {
            "spot_version_id": "v1",
            "spot_id": "s1",
            "breadcrumbs": [{"name": "A"}],
            "travel_details": {"a": 1},
        }
    )

    values = serialize_row_values(row)

    assert values[COLUMNS.index("spot_version_id")] == "v1"
    assert values[COLUMNS.index("breadcrumbs")] == '[{"name": "A"}]'
    assert values[COLUMNS.index("travel_details")] == '{"a": 1}'


def test_build_added_row_reads_raw_and_builds_version(monkeypatch):
    reads = []
    monkeypatch.setattr(
        "discovery_spot_batch_processor.handler._get_json",
        lambda bucket, key: reads.append((bucket, key)) or raw_spot("A", "s1"),
    )

    row = build_added_row(
        bucket="default-bucket",
        run_id="run-1",
        item={
            "spot_id": "s1",
            "raw_bucket": "raw-bucket",
            "raw_key": "raw/s1.json.gz",
            "terminal_status": "success",
        },
        valid_from="2026-05-01T06:10:00Z",
    )

    assert reads == [("raw-bucket", "raw/s1.json.gz")]
    assert row["spot_id"] == "s1"
    assert row["event_type"] == "added"
    assert row["source_raw_key"] == "raw/s1.json.gz"


def test_build_added_rows_reads_success_raw_reports_before_db_transaction(monkeypatch):
    reads = []
    monkeypatch.setattr(
        "discovery_spot_batch_processor.handler._get_json",
        lambda bucket, key: reads.append((bucket, key)) or raw_spot("A", "s1"),
    )

    rows = build_added_rows(
        bucket="default-bucket",
        run_id="run-1",
        success_items=[
            {"spot_id": "s1", "raw_key": "raw/s1.json.gz", "terminal_status": "success"}
        ],
        valid_from="2026-05-01T06:10:00Z",
        max_workers=2,
    )

    assert reads == [("default-bucket", "raw/s1.json.gz")]
    assert rows[0]["spot_id"] == "s1"
    assert rows[0]["event_type"] == "added"
    assert rows[0]["source_raw_key"] == "raw/s1.json.gz"


def test_build_added_rows_propagates_s3_read_failure(monkeypatch):
    monkeypatch.setattr(
        "discovery_spot_batch_processor.handler._get_json",
        lambda *_: (_ for _ in ()).throw(RuntimeError("s3 failed")),
    )

    with pytest.raises(RuntimeError, match="s3 failed"):
        build_added_rows(
            bucket="default-bucket",
            run_id="run-1",
            success_items=[{"spot_id": "s1", "raw_key": "raw/s1.json.gz"}],
            valid_from="2026-05-01T06:10:00Z",
            max_workers=2,
        )


def test_s3_read_workers_uses_env_override(monkeypatch):
    monkeypatch.setenv("DISCOVERY_SPOT_BATCH_S3_READ_WORKERS", "3")

    assert _s3_read_workers() == 3


def test_apply_changes_closes_removed_current_row_and_inserts_tombstone():
    cursor = FakeCursor(
        removed_rows=[{"spot_id": "old", "name": "Old", "content_checksum": "old-checksum"}],
    )
    conn = FakeConnection(cursor)

    apply_spot_version_changes(
        conn=conn,
        run_id="run-1",
        manifest={"removed_spot_ids": ["old"], "sitemap_raw_key": "raw/sitemap.json.gz"},
        added_rows=[],
        valid_from="2026-05-01T06:10:00Z",
    )

    assert conn.committed is True
    assert any(
        sql.startswith("update discovery_spot_versions set is_current=false")
        for sql, _ in cursor.executed
    )
    assert any(sql.startswith("insert into discovery_spot_versions") for sql, _ in cursor.executed)


def test_apply_changes_inserts_added_row_when_no_current_conflict():
    canonical = canonicalize_spot_report(raw_spot("New", "new"), "new")
    added = build_added_spot_version_row(
        canonical_spot=canonical,
        discovery_run_id="run-1",
        source_raw_key="raw/new.json.gz",
        valid_from="now",
    )
    cursor = FakeCursor(existing_by_spot={})
    conn = FakeConnection(cursor)

    apply_spot_version_changes(
        conn=conn,
        run_id="run-1",
        manifest={"removed_spot_ids": [], "sitemap_raw_key": "raw/sitemap.json.gz"},
        added_rows=[added],
        valid_from="now",
    )

    assert conn.committed is True
    assert any(sql.startswith("insert into discovery_spot_versions") for sql, _ in cursor.executed)


def test_apply_changes_skips_idempotent_existing_added_version():
    canonical = canonicalize_spot_report(raw_spot("New", "new"), "new")
    added = build_added_spot_version_row(
        canonical_spot=canonical,
        discovery_run_id="run-1",
        source_raw_key="raw/new.json.gz",
        valid_from="now",
    )
    cursor = FakeCursor(
        existing_by_spot={
            "new": {
                "spot_version_id": added["spot_version_id"],
                "content_checksum": added["content_checksum"],
            }
        }
    )
    conn = FakeConnection(cursor)

    apply_spot_version_changes(
        conn=conn,
        run_id="run-1",
        manifest={"removed_spot_ids": [], "sitemap_raw_key": "raw/sitemap.json.gz"},
        added_rows=[added],
        valid_from="now",
    )

    assert conn.committed is True
    assert not any(
        sql.startswith("insert into discovery_spot_versions") for sql, _ in cursor.executed
    )


def test_apply_changes_raises_on_current_active_conflict_and_rolls_back():
    canonical = canonicalize_spot_report(raw_spot("New", "new"), "new")
    added = build_added_spot_version_row(
        canonical_spot=canonical,
        discovery_run_id="run-1",
        source_raw_key="raw/new.json.gz",
        valid_from="now",
    )
    cursor = FakeCursor(
        existing_by_spot={
            "new": {"spot_version_id": "different-version", "content_checksum": "other"}
        }
    )
    conn = FakeConnection(cursor)

    with pytest.raises(RuntimeError, match="Current active spot conflict for new"):
        apply_spot_version_changes(
            conn=conn,
            run_id="run-1",
            manifest={"removed_spot_ids": [], "sitemap_raw_key": "raw/sitemap.json.gz"},
            added_rows=[added],
            valid_from="now",
        )

    assert conn.rolled_back is True


def test_process_discovery_run_returns_for_missing_or_complete_runs(monkeypatch):
    monkeypatch.setenv("DATA_BUCKET", "bucket")
    assert process_discovery_run("missing", store=FakeStore(run=None)) == "missing_run"
    assert (
        process_discovery_run("done", store=FakeStore(run={"status": "complete"}))
        == "already_complete"
    )


def test_process_discovery_run_completes_when_success_count_matches(monkeypatch):
    monkeypatch.setenv("DATA_BUCKET", "bucket")
    monkeypatch.setenv("SUPABASE_POSTGRES_URL_PARAMETER_NAME", "param")
    applied = []

    @contextmanager
    def fake_connect(parameter_name):
        yield "conn"

    def fake_build_added_rows(**kwargs):
        return [{"spot_id": item["spot_id"]} for item in kwargs["success_items"]]

    monkeypatch.setattr(
        "discovery_spot_batch_processor.handler._get_json",
        lambda *_: {"removed_spot_ids": [], "sitemap_raw_key": "raw/sitemap.json.gz"},
    )
    monkeypatch.setattr("discovery_spot_batch_processor.handler.build_added_rows", fake_build_added_rows)
    monkeypatch.setattr("discovery_spot_batch_processor.handler.connect", fake_connect)
    monkeypatch.setattr(
        "discovery_spot_batch_processor.handler.apply_spot_version_changes",
        lambda **kwargs: applied.append(kwargs),
    )
    store = FakeStore(
        run={
            "status": "spot_processing",
            "planner_manifest_key": "control/manifest.json",
            "success_scrape_count": 2,
        },
        spots=[
            {"spot_id": "a", "terminal_status": "success", "raw_key": "raw/a.json.gz"},
            {"spot_id": "b", "terminal_status": "success", "raw_key": "raw/b.json.gz"},
            {"spot_id": "c", "terminal_status": "failed"},
        ],
    )

    assert process_discovery_run("run-1", store=store) == "processed"

    assert store.completed == ["run-1"]
    assert len(applied) == 1
    assert [row["spot_id"] for row in applied[0]["added_rows"]] == ["a", "b"]


def test_process_discovery_run_raises_when_loaded_success_count_mismatches_run_summary(monkeypatch):
    monkeypatch.setenv("DATA_BUCKET", "bucket")
    monkeypatch.setattr(
        "discovery_spot_batch_processor.handler._get_json",
        lambda *_: {"removed_spot_ids": [], "sitemap_raw_key": "raw/sitemap.json.gz"},
    )
    store = FakeStore(
        run={
            "status": "spot_processing",
            "planner_manifest_key": "control/manifest.json",
            "success_scrape_count": 9062,
        },
        spots=[{"spot_id": "a", "terminal_status": "success", "raw_key": "raw/a.json.gz"}],
    )

    with pytest.raises(RuntimeError, match="Success spot count mismatch"):
        process_discovery_run("run-1", store=store)

    assert store.completed == []


def test_process_discovery_run_raises_when_built_row_count_mismatches_success_items(monkeypatch):
    monkeypatch.setenv("DATA_BUCKET", "bucket")
    monkeypatch.setattr(
        "discovery_spot_batch_processor.handler._get_json",
        lambda *_: {"removed_spot_ids": [], "sitemap_raw_key": "raw/sitemap.json.gz"},
    )
    monkeypatch.setattr("discovery_spot_batch_processor.handler.build_added_rows", lambda **_: [])
    store = FakeStore(
        run={
            "status": "spot_processing",
            "planner_manifest_key": "control/manifest.json",
            "success_scrape_count": 1,
        },
        spots=[{"spot_id": "a", "terminal_status": "success", "raw_key": "raw/a.json.gz"}],
    )

    with pytest.raises(RuntimeError, match="Added row count mismatch"):
        process_discovery_run("run-1", store=store)

    assert store.completed == []


def test_apply_changes_closes_current_removed_tombstone_when_spot_is_readded():
    canonical = canonicalize_spot_report(
        raw_spot("Readded Spot", "readded"),
        "readded",
    )
    added = build_added_spot_version_row(
        canonical_spot=canonical,
        discovery_run_id="run-2",
        source_raw_key="raw/readded.json.gz",
        valid_from="2026-05-01T06:10:00Z",
    )

    current_removed_tombstone = {
        "spot_version_id": "old-removed-version",
        "spot_id": "readded",
        "event_type": "removed",
        "is_current": True,
        "content_checksum": "old-checksum",
    }

    cursor = FakeCursor(existing_by_spot={"readded": current_removed_tombstone})
    conn = FakeConnection(cursor)

    apply_spot_version_changes(
        conn=conn,
        run_id="run-2",
        manifest={"removed_spot_ids": [], "sitemap_raw_key": "raw/sitemap.json.gz"},
        added_rows=[added],
        valid_from="2026-05-01T06:10:00Z",
    )

    assert conn.committed is True
    update_statements = [
        (sql, params)
        for sql, params in cursor.executed
        if sql.startswith("update discovery_spot_versions set is_current=false")
    ]
    insert_statements = [
        (sql, params)
        for sql, params in cursor.executed
        if sql.startswith("insert into discovery_spot_versions")
    ]

    assert update_statements == [
        (
            "update discovery_spot_versions set is_current=false, valid_to=%s where spot_id = any(%s) and is_current=true and event_type='removed'",
            ("2026-05-01T06:10:00Z", ["readded"]),
        )
    ]
    assert len(insert_statements) == 1


def test_apply_changes_skips_insert_when_current_added_version_already_exists():
    canonical = canonicalize_spot_report(
        raw_spot("Existing", "existing"),
        "existing",
    )
    added = build_added_spot_version_row(
        canonical_spot=canonical,
        discovery_run_id="run-1",
        source_raw_key="raw/existing.json.gz",
        valid_from="now",
    )
    cursor = FakeCursor(
        existing_by_spot={
            "existing": {
                "spot_version_id": added["spot_version_id"],
                "event_type": "added",
                "content_checksum": added["content_checksum"],
            }
        }
    )
    conn = FakeConnection(cursor)

    apply_spot_version_changes(
        conn=conn,
        run_id="run-1",
        manifest={"removed_spot_ids": [], "sitemap_raw_key": "raw/sitemap.json.gz"},
        added_rows=[added],
        valid_from="now",
    )

    assert conn.committed is True
    assert not any(
        sql.startswith("insert into discovery_spot_versions") for sql, _ in cursor.executed
    )


def test_should_process_run_returns_missing_for_missing_run():
    store = FakeStore(run=None)

    assert should_process_run("run-1", store) == "missing_run"
    assert store.transitions == []


def test_should_process_run_returns_already_complete_for_complete_run():
    store = FakeStore(run={"status": "complete"})

    assert should_process_run("run-1", store) == "already_complete"
    assert store.transitions == []


def test_should_process_run_processes_run_already_in_processing_state():
    store = FakeStore(run={"status": "spot_processing"})

    assert should_process_run("run-1", store) == "process"
    assert store.transitions == []


def test_should_process_run_claims_queued_run_before_processing():
    store = FakeStore(run={"status": "spot_processing_queued"})

    assert should_process_run("run-1", store) == "process"
    assert store.transitions == [
        {
            "discovery_run_id": "run-1",
            "from_status": "spot_processing_queued",
            "to_status": "spot_processing",
            "extra_attributes": None,
        }
    ]


def test_should_process_run_returns_claim_lost_when_queued_transition_fails():
    store = FakeStore(run={"status": "spot_processing_queued"}, transition_result=False)

    assert should_process_run("run-1", store) == "claim_lost"
    assert store.transitions == [
        {
            "discovery_run_id": "run-1",
            "from_status": "spot_processing_queued",
            "to_status": "spot_processing",
            "extra_attributes": None,
        }
    ]


def test_should_process_run_rejects_invalid_status():
    store = FakeStore(run={"status": "waiting_for_spot_scrapes"})

    assert should_process_run("run-1", store) == "invalid_status:waiting_for_spot_scrapes"
    assert store.transitions == []


def test_lambda_handler_claims_and_processes_queued_run_once(monkeypatch):
    store = FakeStore(run={"status": "spot_processing_queued"})
    processed = []

    monkeypatch.setattr("discovery_spot_batch_processor.handler._store", lambda: store)
    monkeypatch.setattr(
        "discovery_spot_batch_processor.handler.process_discovery_run",
        lambda run_id, store: processed.append(run_id) or "processed",
    )

    result = lambda_handler(
        {"Records": [{"body": '{"discovery_run_id": "run-1"}'}]},
        None,
    )

    assert processed == ["run-1"]
    assert store.transitions == [
        {
            "discovery_run_id": "run-1",
            "from_status": "spot_processing_queued",
            "to_status": "spot_processing",
            "extra_attributes": None,
        }
    ]
    assert result["statusCode"] == 200


def test_lambda_handler_does_not_process_invalid_status(monkeypatch):
    store = FakeStore(run={"status": "waiting_for_spot_scrapes"})
    processed = []

    monkeypatch.setattr(
        "discovery_spot_batch_processor.handler._store",
        lambda: store,
    )
    monkeypatch.setattr(
        "discovery_spot_batch_processor.handler.process_discovery_run",
        lambda run_id, store: processed.append(run_id) or "processed",
    )

    result = lambda_handler(
        {
            "Records": [
                {
                    "body": '{"discovery_run_id": "run-1"}',
                }
            ]
        },
        None,
    )

    assert processed == []
    assert store.transitions == []

    body = __import__("json").loads(result["body"])
    assert body == {"results": ["invalid_status:waiting_for_spot_scrapes"]}
