import pytest

from discovery_completion.handler import build_batch_processor_message, process_completion_message


class FakeStore:
    def __init__(self, *, mark_result=True, run=None, transitions=None):
        self.mark_result = mark_result
        self.run = run
        self.transitions = transitions or []
        self.mark_calls = []
        self.transition_calls = []

    def mark_spot_terminal(self, **kwargs):
        self.mark_calls.append(kwargs)
        return self.mark_result

    def get_run(self, discovery_run_id):
        return self.run

    def transition_run_status(self, **kwargs):
        self.transition_calls.append(kwargs)
        if self.transitions:
            return self.transitions.pop(0)
        return False


def _success_payload(**overrides):
    payload = {
        "schema_version": 1,
        "message_type": "spot_scrape_complete",
        "terminal_status": "success",
        "discovery_run_id": "run-1",
        "scrape_date": "2026-05-01",
        "spot_id": "spot-a",
        "raw_bucket": "data-bucket",
        "raw_key": "raw/spot_report/x.json.gz",
        "completed_at": "2026-05-01T06:02:10Z",
    }
    payload.update(overrides)
    return payload


def test_build_batch_processor_message_shape():
    assert build_batch_processor_message(discovery_run_id="run-1", requested_at="now") == {
        "schema_version": 1,
        "message_type": "discovery_spot_batch_process_requested",
        "discovery_run_id": "run-1",
        "requested_at": "now",
    }


def test_success_completion_records_terminal_fields_without_queueing(monkeypatch):
    sent = []
    store = FakeStore(run={"terminal_scrape_count": 1, "expected_spot_count": 2})
    monkeypatch.setattr(
        "discovery_completion.handler._send_batch_processor_request",
        lambda **kwargs: sent.append(kwargs),
    )

    result = process_completion_message(_success_payload(), store=store)

    assert result == "recorded"
    assert store.mark_calls == [
        {
            "discovery_run_id": "run-1",
            "spot_id": "spot-a",
            "terminal_status": "success",
            "completed_at": "2026-05-01T06:02:10Z",
            "raw_key": "raw/spot_report/x.json.gz",
            "raw_bucket": "data-bucket",
            "failure_reason": None,
            "failure_source": None,
        }
    ]
    assert store.transition_calls == []
    assert sent == []


def test_duplicate_completion_does_not_fetch_run_or_queue(monkeypatch):
    sent = []
    store = FakeStore(mark_result=False)
    monkeypatch.setattr(
        "discovery_completion.handler._send_batch_processor_request",
        lambda **kwargs: sent.append(kwargs),
    )

    result = process_completion_message(_success_payload(), store=store)

    assert result == "duplicate"
    assert store.transition_calls == []
    assert sent == []


def test_last_terminal_completion_transitions_and_queues_once(monkeypatch):
    sent = []
    store = FakeStore(
        run={"terminal_scrape_count": 2, "expected_spot_count": 2},
        transitions=[True, True],
    )
    monkeypatch.setattr(
        "discovery_completion.handler._send_batch_processor_request",
        lambda **kwargs: sent.append(kwargs),
    )

    result = process_completion_message(_success_payload(), store=store)

    assert result == "queued_batch_processor"
    assert [call["to_status"] for call in store.transition_calls] == [
        "spot_scrapes_complete",
        "spot_processing_queued",
    ]
    assert sent == [{"discovery_run_id": "run-1"}]


def test_loser_of_status_transition_does_not_queue(monkeypatch):
    sent = []
    store = FakeStore(
        run={"terminal_scrape_count": 2, "expected_spot_count": 2},
        transitions=[False],
    )
    monkeypatch.setattr(
        "discovery_completion.handler._send_batch_processor_request",
        lambda **kwargs: sent.append(kwargs),
    )

    result = process_completion_message(_success_payload(), store=store)

    assert result == "recorded"
    assert len(store.transition_calls) == 1
    assert sent == []


def test_failure_completion_records_failure_fields(monkeypatch):
    store = FakeStore(run={"terminal_scrape_count": 1, "expected_spot_count": 2})
    payload = _success_payload(
        terminal_status="failed",
        raw_bucket=None,
        raw_key=None,
        completed_at=None,
        failed_at="2026-05-01T06:03:10Z",
        failure_reason="HTTP 403",
        failure_source="spot_scraper",
    )

    result = process_completion_message(payload, store=store)

    assert result == "recorded"
    assert store.mark_calls[0]["terminal_status"] == "failed"
    assert store.mark_calls[0]["completed_at"] == "2026-05-01T06:03:10Z"
    assert store.mark_calls[0]["failure_reason"] == "HTTP 403"


def test_missing_run_after_terminal_write_raises():
    store = FakeStore(run=None)

    with pytest.raises(FileNotFoundError):
        process_completion_message(_success_payload(), store=store)
