import json

import pytest

from forecast_scraper.completion import CompletionSender
from forecast_scraper.raw import build_raw_envelope, build_raw_key
from forecast_scraper.scraper import core
import forecast_scraper.handler as handler


REQUEST = {
    "schema_version": 1,
    "forecast_run_id": "forecast#offset=-10#scrape_date=2026-05-22#time=04-00",
    "scheduled_utc_time": "2026-05-22T14:00:00+00:00",
    "scrape_date": "2026-05-22",
    "spot_id": "spot-a",
    "spot_version_id": "version-a",
    "spot_name": "Spot A",
    "utc_offset": -10,
    "timezone": "Pacific/Honolulu",
    "latitude": 1.25,
    "longitude": 2.5,
    "raw_bucket": "raw-bucket",
}


class CompletionSpy:
    def __init__(self):
        self.successes = []
        self.failures = []

    def send_success(self, **kwargs):
        self.successes.append(kwargs)

    def send_failure(self, **kwargs):
        self.failures.append(kwargs)


def test_endpoint_selection_excludes_weather_and_sunlight_and_tides_are_feet():
    assert list(core.ENDPOINTS) == ["rating", "tides", "wave", "wind"]
    assert "weather" not in core.ENDPOINTS
    assert "sunlight" not in core.ENDPOINTS
    assert "units[tideHeight]=FT" in core.ENDPOINTS["tides"]


def test_scrape_forecast_is_all_or_nothing(monkeypatch):
    calls = []

    def fake_request(url):
        calls.append(url)
        if "wave" in url:
            raise RuntimeError("wave failed")
        return object()

    monkeypatch.setattr(core, "make_request", fake_request)
    monkeypatch.setattr(core, "parse_response", lambda response: {"ok": True})

    with pytest.raises(RuntimeError, match="wave failed"):
        core.scrape_forecast("spot-a")

    assert len(calls) == 3


def test_raw_key_construction():
    assert build_raw_key(
        scrape_date="2026-05-22",
        utc_offset=-10,
        forecast_run_id="forecast#offset=-10#scrape_date=2026-05-22#time=04-00",
        spot_id="spot-a",
    ) == (
        "raw/forecast/scrape_date=2026-05-22/utc_offset=-10/"
        "forecast_run_id=forecast#offset=-10#scrape_date=2026-05-22#time=04-00/"
        "spot_id=spot-a.json.gz"
    )


def test_raw_envelope_has_only_scheduled_and_scraped_time_fields():
    envelope = build_raw_envelope(request=REQUEST, payload={"rating": {}}, scraped_at="now")

    assert envelope["schema_version"] == 1
    assert isinstance(envelope["schema_version"], int)
    assert envelope["scheduled_utc_time"] == REQUEST["scheduled_utc_time"]
    assert envelope["scraped_at"] == "now"
    assert envelope["raw_payload"] == {"rating": {}}
    assert "local_date" not in envelope
    assert "local_scrape_time" not in envelope
    assert "scrape_date" not in envelope
    assert "created_at" not in envelope


def test_process_record_success_writes_raw_and_sends_success(monkeypatch):
    completion = CompletionSpy()
    writes = []

    monkeypatch.setattr(handler, "scrape_forecast", lambda spot_id: {"rating": {}, "tides": {}, "wave": {}, "wind": {}})
    monkeypatch.setattr(handler, "utc_now_iso", lambda: "2026-05-22T14:01:00Z")
    monkeypatch.setattr(handler.s3_writer, "put_json", lambda **kwargs: writes.append(kwargs))

    assert handler.process_record(REQUEST, completion_sender=completion) == "success"

    assert writes[0]["bucket"] == "raw-bucket"
    assert writes[0]["key"].endswith("spot_id=spot-a.json.gz")
    assert writes[0]["body"]["scheduled_utc_time"] == REQUEST["scheduled_utc_time"]
    assert completion.successes[0]["request"]["schema_version"] == 1
    assert isinstance(completion.successes[0]["request"]["schema_version"], int)
    assert completion.successes[0]["raw_bucket"] == "raw-bucket"
    assert completion.successes[0]["raw_key"] == writes[0]["key"]
    assert completion.failures == []


def test_process_record_caught_scrape_failure_sends_failure_and_writes_no_raw(monkeypatch):
    completion = CompletionSpy()
    writes = []

    def fail(_spot_id):
        raise ValueError("bad json")

    monkeypatch.setattr(handler, "scrape_forecast", fail)
    monkeypatch.setattr(handler.s3_writer, "put_json", lambda **kwargs: writes.append(kwargs))

    assert handler.process_record(REQUEST, completion_sender=completion) == "failed"

    assert writes == []
    assert completion.successes == []
    assert completion.failures[0]["failure_source"] == "parse"
    assert completion.failures[0]["failure_reason"] == "bad json"


def test_failed_completion_message_has_null_raw_lineage():
    sent = []

    class FakeSqs:
        def send_message(self, **kwargs):
            sent.append(json.loads(kwargs["MessageBody"]))

    sender = CompletionSender(queue_url="completion-queue", sqs_client=FakeSqs())
    sender.send_failure(request=REQUEST, failure_source="parse", failure_reason="bad json")

    assert sent[0]["schema_version"] == 1
    assert isinstance(sent[0]["schema_version"], int)
    assert sent[0]["raw_bucket"] is None
    assert sent[0]["raw_key"] is None


def test_completion_send_failure_raises(monkeypatch):
    class BrokenCompletion(CompletionSpy):
        def send_failure(self, **kwargs):
            raise RuntimeError("sqs down")

    monkeypatch.setattr(handler, "scrape_forecast", lambda _spot_id: (_ for _ in ()).throw(ValueError("bad")))

    with pytest.raises(RuntimeError, match="sqs down"):
        handler.process_record(REQUEST, completion_sender=BrokenCompletion())
