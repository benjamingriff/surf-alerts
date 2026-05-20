from discovery_run_planner.handler import (
    build_planner_manifest,
    classify_spots,
    process_sitemap_completion,
)


class FakeStore:
    def __init__(self, create_result=True):
        self.create_result = create_result
        self.updated = None
        self.seeded = None

    def create_run_if_absent(self, **kwargs):
        self.created = kwargs
        return self.create_result

    def update_run_plan(self, **kwargs):
        self.updated = kwargs

    def seed_spots(self, **kwargs):
        self.seeded = kwargs


def test_classify_spots_computes_added_removed_existing():
    result = classify_spots({"a", "b", "c"}, {"b", "c", "d"})
    assert result == {
        "added_spot_ids": ["a"],
        "removed_spot_ids": ["d"],
        "existing_spot_count": 2,
        "added_count": 1,
        "removed_count": 1,
    }


def test_build_planner_manifest_includes_counts_and_raw_reference():
    manifest = build_planner_manifest(
        discovery_run_id="run-1",
        scrape_date="2026-05-01",
        raw_bucket="bucket",
        raw_key="raw/sitemap/x.json.gz",
        classification={
            "added_spot_ids": ["a"],
            "removed_spot_ids": [],
            "existing_spot_count": 2,
            "added_count": 1,
            "removed_count": 0,
        },
        planned_at="2026-05-01T06:00:00Z",
    )
    assert manifest["schema_version"] == 1
    assert manifest["sitemap_raw_bucket"] == "bucket"
    assert manifest["added_count"] == 1


def test_duplicate_run_exits_before_s3_or_postgres(monkeypatch):
    fake_store = FakeStore(create_result=False)
    monkeypatch.setattr("discovery_run_planner.handler._store", lambda: fake_store)
    monkeypatch.setattr(
        "discovery_run_planner.handler._get_json",
        lambda *_: (_ for _ in ()).throw(AssertionError("should not read s3")),
    )

    result = process_sitemap_completion(
        {
            "discovery_run_id": "run-1",
            "scrape_date": "2026-05-01",
            "raw_bucket": "bucket",
            "raw_key": "raw/sitemap/x.json.gz",
        }
    )

    assert result == "duplicate"


def test_no_op_run_writes_manifest_and_marks_no_op(monkeypatch):
    fake_store = FakeStore()
    put_calls = []
    monkeypatch.setenv("DATA_BUCKET", "data-bucket")
    monkeypatch.setattr("discovery_run_planner.handler._store", lambda: fake_store)
    monkeypatch.setattr("discovery_run_planner.handler._get_json", lambda *_: {"spots": ["a"]})
    monkeypatch.setattr("discovery_run_planner.handler._current_active_ids", lambda: {"a"})
    monkeypatch.setattr(
        "discovery_run_planner.handler._put_json",
        lambda bucket, key, body: put_calls.append((bucket, key, body)),
    )

    result = process_sitemap_completion(
        {
            "discovery_run_id": "run-1",
            "scrape_date": "2026-05-01",
            "raw_bucket": "raw-bucket",
            "raw_key": "raw/sitemap/x.json.gz",
        }
    )

    assert result == "no_op"
    assert fake_store.updated["status"] == "no_op_complete"
    assert fake_store.updated["expected_spot_count"] == 0
    assert put_calls[0][2]["existing_spot_count"] == 1
