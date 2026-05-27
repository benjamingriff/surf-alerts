import json
from datetime import datetime, timezone

import forecast_run_planner.handler as h


def test_parse_local_scrape_time_requires_canonical_hour_format():
    assert h.parse_local_scrape_time("04:00") == (4, 0)

    for value in ["4:00", "004:00", "04:30", "24:00"]:
        try:
            h.parse_local_scrape_time(value)
        except ValueError as error:
            assert str(error) == "FORECAST_SCRAPE_LOCAL_TIME must be HH:00 for v1"
        else:
            raise AssertionError(f"expected ValueError for {value}")


def test_due_offsets_and_date_boundary():
    scheduled = datetime(2026, 5, 22, 14, tzinfo=timezone.utc)
    assert h.due_utc_offsets(
        scheduled_utc_time=scheduled,
        local_scrape_time="04:00",
        min_offset=-12,
        max_offset=14,
    ) == [-10, 14]
    assert (
        scheduled.replace(tzinfo=None) if False else scheduled
    ).date().isoformat() == "2026-05-22"


def test_parse_scheduled_time_requires_utc():
    assert h.parse_scheduled_time("2026-05-22T14:00:00Z").isoformat() == "2026-05-22T14:00:00+00:00"

    try:
        h.parse_scheduled_time("2026-05-22T14:00:00")
    except ValueError as error:
        assert str(error) == "EventBridge time must be UTC"
    else:
        raise AssertionError("expected ValueError")


def test_forecast_run_id_is_deterministic():
    assert (
        h.forecast_run_id(utc_offset=-10, scrape_date="2026-05-22", local_scrape_time="04:00")
        == "forecast#offset=-10#scrape_date=2026-05-22#time=04-00"
    )


class FakeStore:
    def __init__(self, created=True, existing_run=None):
        self.created = created
        self.existing_run = existing_run
        self.calls = []

    def create_run_if_absent(self, **kwargs):
        self.calls.append(("create", kwargs))
        return self.created

    def get_run(self, forecast_run_id):
        self.calls.append(("get", forecast_run_id))
        return self.existing_run

    def seed_spots(self, **kwargs):
        self.calls.append(("seed", kwargs))

    def mark_run_in_progress(self, *args):
        self.calls.append(("in_progress", args))


def test_empty_offset_exits_before_control_writes(monkeypatch):
    store = FakeStore()
    monkeypatch.setenv("FORECAST_SCRAPER_QUEUE_URL", "queue")
    monkeypatch.setenv("FORECAST_MIN_UTC_OFFSET", "-10")
    monkeypatch.setenv("FORECAST_MAX_UTC_OFFSET", "-10")
    monkeypatch.setattr(h, "_live_spots_for_offset", lambda offset: [])
    monkeypatch.setattr(h, "_store", lambda: store)

    assert h.plan_forecast_runs({"time": "2026-05-22T14:00:00Z"}) == [
        {"utc_offset": -10, "result": "empty_offset"}
    ]
    assert store.calls == []


def test_duplicate_in_progress_run_exits_before_seed_or_enqueue(monkeypatch):
    store = FakeStore(created=False, existing_run={"status": "in_progress"})
    monkeypatch.setenv("FORECAST_SCRAPER_QUEUE_URL", "queue")
    monkeypatch.setenv("FORECAST_MIN_UTC_OFFSET", "-10")
    monkeypatch.setenv("FORECAST_MAX_UTC_OFFSET", "-10")
    monkeypatch.setattr(
        h, "_live_spots_for_offset", lambda offset: [{"spot_id": "s1", "utc_offset": -10}]
    )
    monkeypatch.setattr(h, "_store", lambda: store)
    monkeypatch.setattr(
        h,
        "_queue_scrapes",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("queued")),
    )

    assert h.plan_forecast_runs({"time": "2026-05-22T14:00:00Z"}) == [
        {
            "utc_offset": -10,
            "forecast_run_id": "forecast#offset=-10#scrape_date=2026-05-22#time=04-00",
            "result": "duplicate",
        }
    ]
    assert [c[0] for c in store.calls] == ["create", "get"]


def test_duplicate_planned_run_retries_seed_and_enqueue(monkeypatch):
    store = FakeStore(created=False, existing_run={"status": "planned"})
    queued = []
    monkeypatch.setenv("FORECAST_SCRAPER_QUEUE_URL", "queue")
    monkeypatch.setenv("FORECAST_MIN_UTC_OFFSET", "-10")
    monkeypatch.setenv("FORECAST_MAX_UTC_OFFSET", "-10")
    monkeypatch.setattr(
        h, "_live_spots_for_offset", lambda offset: [{"spot_id": "s1", "utc_offset": -10}]
    )
    monkeypatch.setattr(h, "_store", lambda: store)
    monkeypatch.setattr(h, "_queue_scrapes", lambda **kwargs: queued.append(kwargs))

    assert h.plan_forecast_runs({"time": "2026-05-22T14:00:00Z"}) == [
        {
            "utc_offset": -10,
            "forecast_run_id": "forecast#offset=-10#scrape_date=2026-05-22#time=04-00",
            "result": "retried_planned",
        }
    ]
    assert [c[0] for c in store.calls] == ["create", "get", "seed", "in_progress"]
    assert store.calls[2][1]["overwrite_existing"] is False
    assert len(queued) == 1


def test_seed_happens_before_enqueue_and_message_shape(monkeypatch):
    store = FakeStore()
    order = []
    sent = []
    spot = {
        "spot_id": "s1",
        "spot_version_id": "v1",
        "name": "Spot",
        "utc_offset": -10,
        "timezone": "Pacific/Honolulu",
        "latitude": 1.2,
        "longitude": 3.4,
    }

    class Sqs:
        def send_message_batch(self, **kwargs):
            order.append("enqueue")
            sent.extend(kwargs["Entries"])
            return {}

    def seed_spots(**kwargs):
        order.append("seed")
        store.calls.append(("seed", kwargs))

    store.seed_spots = seed_spots
    monkeypatch.setenv("FORECAST_SCRAPER_QUEUE_URL", "queue")
    monkeypatch.setenv("FORECAST_MIN_UTC_OFFSET", "-10")
    monkeypatch.setenv("FORECAST_MAX_UTC_OFFSET", "-10")
    monkeypatch.setattr(h, "_live_spots_for_offset", lambda offset: [spot])
    monkeypatch.setattr(h, "_store", lambda: store)
    monkeypatch.setattr(h, "_sqs", lambda: Sqs())

    assert h.plan_forecast_runs({"time": "2026-05-22T14:00:00Z"}) == [
        {
            "utc_offset": -10,
            "forecast_run_id": "forecast#offset=-10#scrape_date=2026-05-22#time=04-00",
            "result": "planned",
        }
    ]
    assert order == ["seed", "enqueue"]
    assert store.calls[1][1]["overwrite_existing"] is True
    assert store.calls[-1][0] == "in_progress"
    body = json.loads(sent[0]["MessageBody"])
    assert body == {
        "schema_version": 1,
        "message_type": "forecast_spot_scrape_requested",
        "forecast_run_id": "forecast#offset=-10#scrape_date=2026-05-22#time=04-00",
        "scheduled_utc_time": "2026-05-22T14:00:00+00:00",
        "scrape_date": "2026-05-22",
        "local_date": "2026-05-22",
        "local_scrape_time": "04:00",
        "spot_id": "s1",
        "spot_version_id": "v1",
        "spot_name": "Spot",
        "utc_offset": -10,
        "timezone": "Pacific/Honolulu",
        "latitude": 1.2,
        "longitude": 3.4,
    }


def test_multiple_due_offsets_plan_independent_runs(monkeypatch):
    store = FakeStore()
    monkeypatch.setenv("FORECAST_SCRAPER_QUEUE_URL", "queue")
    monkeypatch.setenv("FORECAST_MIN_UTC_OFFSET", "-12")
    monkeypatch.setenv("FORECAST_MAX_UTC_OFFSET", "14")
    monkeypatch.setattr(
        h,
        "_live_spots_for_offset",
        lambda offset: [{"spot_id": f"s{offset}", "utc_offset": offset}],
    )
    monkeypatch.setattr(h, "_store", lambda: store)
    monkeypatch.setattr(h, "_queue_scrapes", lambda **kwargs: None)

    results = h.plan_forecast_runs({"time": "2026-05-22T14:00:00Z"})

    assert [result["utc_offset"] for result in results] == [-10, 14]
    assert [call[1]["utc_offset"] for call in store.calls if call[0] == "create"] == [-10, 14]
