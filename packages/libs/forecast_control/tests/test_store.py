from datetime import datetime, timedelta, timezone

import boto3
import pytest
from botocore.exceptions import ClientError
from moto import mock_aws

from forecast_control.store import ForecastControlStore


def create_table():
    dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
    table = dynamodb.create_table(
        TableName="forecast-control-test",
        KeySchema=[
            {"AttributeName": "pk", "KeyType": "HASH"},
            {"AttributeName": "sk", "KeyType": "RANGE"},
        ],
        AttributeDefinitions=[
            {"AttributeName": "pk", "AttributeType": "S"},
            {"AttributeName": "sk", "AttributeType": "S"},
        ],
        BillingMode="PAY_PER_REQUEST",
    )
    table.wait_until_exists()
    return dynamodb, table


@mock_aws
def test_create_run_if_absent_writes_run_once_with_initial_control_state():
    dynamodb, table = create_table()
    store = ForecastControlStore(
        table_name="forecast-control-test", dynamodb_resource=dynamodb, ttl_days=7
    )

    created = store.create_run_if_absent(
        forecast_run_id="forecast#offset=-10#scrape_date=2026-05-22#time=04-00",
        scrape_date="2026-05-22",
        scheduled_utc_time="2026-05-22T14:00:00+00:00",
        local_scrape_time="04:00",
        local_date="2026-05-22",
        utc_offset=-10,
        expected_scrape_count=2,
    )
    duplicate = store.create_run_if_absent(
        forecast_run_id="forecast#offset=-10#scrape_date=2026-05-22#time=04-00",
        scrape_date="2026-05-22",
        scheduled_utc_time="2026-05-22T14:00:00+00:00",
        local_scrape_time="04:00",
        local_date="2026-05-22",
        utc_offset=-10,
        expected_scrape_count=2,
    )

    item = table.get_item(
        Key={
            "pk": "FORECAST_RUN#forecast#offset=-10#scrape_date=2026-05-22#time=04-00",
            "sk": "RUN",
        }
    )["Item"]
    assert created is True
    assert duplicate is False
    assert item["status"] == "planned"
    assert item["scrape_status"] == "in_progress"
    assert item["processing_status"] == "not_started"
    assert item["expected_scrape_count"] == 2
    assert item["terminal_scrape_count"] == 0
    assert item["successful_scrape_count"] == 0
    assert item["failed_scrape_count"] == 0
    assert item["expected_processing_count"] == 0
    assert item["terminal_processing_count"] == 0
    assert item["expires_at"] > 0


@mock_aws
def test_seed_spots_can_overwrite_on_initial_planning_and_get_run_reads_by_run_key(monkeypatch):
    dynamodb, table = create_table()
    store = ForecastControlStore(table_name="forecast-control-test", dynamodb_resource=dynamodb)
    run_id = "forecast#offset=-10#scrape_date=2026-05-22#time=04-00"
    store.create_run_if_absent(
        forecast_run_id=run_id,
        scrape_date="2026-05-22",
        scheduled_utc_time="2026-05-22T14:00:00+00:00",
        local_scrape_time="04:00",
        local_date="2026-05-22",
        utc_offset=-10,
        expected_scrape_count=1,
    )

    spots = [{"spot_id": "s1", "spot_version_id": "v1"}]
    store.seed_spots(forecast_run_id=run_id, spots=spots)
    table.update_item(
        Key=store.spot_key(run_id, "s1"),
        UpdateExpression="SET scrape_status=:status",
        ExpressionAttributeValues={":status": "complete"},
    )
    store.seed_spots(forecast_run_id=run_id, spots=spots)

    captured = []
    original_get_item = store.table.get_item

    def capture_get_item(**kwargs):
        captured.append(kwargs)
        return original_get_item(**kwargs)

    monkeypatch.setattr(store.table, "get_item", capture_get_item)

    run = store.get_run(run_id, consistent_read=True)
    spot = table.get_item(Key=store.spot_key(run_id, "s1"))["Item"]
    assert captured[0]["ConsistentRead"] is True
    assert run is not None
    assert run["forecast_run_id"] == run_id
    assert spot["item_type"] == "forecast_planned_spot"
    assert spot["spot_id"] == "s1"
    assert spot["spot_version_id"] == "v1"
    assert spot["scrape_status"] == "planned"
    assert spot["processing_status"] == "not_started"


@mock_aws
def test_seed_spots_can_skip_existing_items_on_duplicate_planned_retry():
    dynamodb, table = create_table()
    store = ForecastControlStore(table_name="forecast-control-test", dynamodb_resource=dynamodb)
    run_id = "forecast#offset=-10#scrape_date=2026-05-22#time=04-00"
    spots = [{"spot_id": "s1", "spot_version_id": "v1"}]
    store.seed_spots(forecast_run_id=run_id, spots=spots)
    table.update_item(
        Key=store.spot_key(run_id, "s1"),
        UpdateExpression="SET scrape_status=:status, failure_reason=:reason",
        ExpressionAttributeValues={":status": "failed", ":reason": "timeout"},
    )

    store.seed_spots(forecast_run_id=run_id, spots=spots, overwrite_existing=False)

    spot = table.get_item(Key=store.spot_key(run_id, "s1"))["Item"]
    assert spot["scrape_status"] == "failed"
    assert spot["failure_reason"] == "timeout"


@mock_aws
def test_mark_run_in_progress_returns_true_once_then_false_for_racing_duplicate():
    dynamodb, table = create_table()
    store = ForecastControlStore(table_name="forecast-control-test", dynamodb_resource=dynamodb)
    run_id = "forecast#offset=-10#scrape_date=2026-05-22#time=04-00"
    store.create_run_if_absent(
        forecast_run_id=run_id,
        scrape_date="2026-05-22",
        scheduled_utc_time="2026-05-22T14:00:00+00:00",
        local_scrape_time="04:00",
        local_date="2026-05-22",
        utc_offset=-10,
        expected_scrape_count=1,
    )

    first = store.mark_run_in_progress(run_id)
    second = store.mark_run_in_progress(run_id)

    item = table.get_item(Key=store.run_key(run_id))["Item"]
    assert first is True
    assert second is False
    assert item["status"] == "in_progress"


@mock_aws
def test_record_scrape_terminal_success_increments_run_once_and_duplicate_is_ignored(monkeypatch):
    dynamodb, table = create_table()
    store = ForecastControlStore(table_name="forecast-control-test", dynamodb_resource=dynamodb)
    run_id = "forecast#offset=-10#scrape_date=2026-05-22#time=04-00"
    store.create_run_if_absent(
        forecast_run_id=run_id,
        scrape_date="2026-05-22",
        scheduled_utc_time="2026-05-22T14:00:00+00:00",
        local_scrape_time="04:00",
        local_date="2026-05-22",
        utc_offset=-10,
        expected_scrape_count=1,
    )
    store.seed_spots(forecast_run_id=run_id, spots=[{"spot_id": "s1", "spot_version_id": "v1"}])

    first = store.record_scrape_terminal(
        forecast_run_id=run_id,
        spot_id="s1",
        scrape_status="success",
        raw_bucket="bucket",
        raw_key="key.json.gz",
        scraped_at="2026-05-22T14:01:00+00:00",
    )
    duplicate = store.record_scrape_terminal(
        forecast_run_id=run_id,
        spot_id="s1",
        scrape_status="success",
        raw_bucket="bucket",
        raw_key="key.json.gz",
        scraped_at="2026-05-22T14:01:00+00:00",
    )

    run = table.get_item(Key=store.run_key(run_id))["Item"]
    spot = table.get_item(Key=store.spot_key(run_id, "s1"))["Item"]
    assert first is True
    assert duplicate is False
    assert spot["scrape_status"] == "success"
    assert spot["raw_key"] == "key.json.gz"
    assert run["terminal_scrape_count"] == 1
    assert run["successful_scrape_count"] == 1
    assert run["expected_processing_count"] == 1


@mock_aws
def test_record_scrape_terminal_uses_resource_update_item_not_transaction(monkeypatch):
    dynamodb, table = create_table()
    store = ForecastControlStore(table_name="forecast-control-test", dynamodb_resource=dynamodb)
    run_id = "forecast#offset=-10#scrape_date=2026-05-22#time=04-00"
    store.create_run_if_absent(
        forecast_run_id=run_id,
        scrape_date="2026-05-22",
        scheduled_utc_time="2026-05-22T14:00:00+00:00",
        local_scrape_time="04:00",
        local_date="2026-05-22",
        utc_offset=-10,
        expected_scrape_count=1,
    )
    store.seed_spots(forecast_run_id=run_id, spots=[{"spot_id": "s1", "spot_version_id": "v1"}])

    def fail_transaction(**kwargs):
        raise AssertionError("record_scrape_terminal should not call TransactWriteItems")

    monkeypatch.setattr(store.dynamodb.meta.client, "transact_write_items", fail_transaction)

    assert (
        store.record_scrape_terminal(
            forecast_run_id=run_id,
            spot_id="s1",
            scrape_status="success",
            raw_bucket="bucket",
            raw_key="key.json.gz",
            scraped_at="2026-05-22T14:01:00+00:00",
        )
        is True
    )

    run = table.get_item(Key=store.run_key(run_id))["Item"]
    spot = table.get_item(Key=store.spot_key(run_id, "s1"))["Item"]
    assert spot["scrape_status"] == "success"
    assert spot["raw_key"] == "key.json.gz"
    assert run["terminal_scrape_count"] == 1
    assert run["successful_scrape_count"] == 1
    assert run["expected_processing_count"] == 1


@mock_aws
def test_mark_processing_terminal_uses_resource_update_item_not_transaction(monkeypatch):
    dynamodb, table = create_table()
    store = ForecastControlStore(table_name="forecast-control-test", dynamodb_resource=dynamodb)
    run_id = "forecast#offset=-10#scrape_date=2026-05-22#time=04-00"
    store.create_run_if_absent(
        forecast_run_id=run_id,
        scrape_date="2026-05-22",
        scheduled_utc_time="2026-05-22T14:00:00+00:00",
        local_scrape_time="04:00",
        local_date="2026-05-22",
        utc_offset=-10,
        expected_scrape_count=1,
    )
    store.seed_spots(forecast_run_id=run_id, spots=[{"spot_id": "s1", "spot_version_id": "v1"}])
    table.update_item(
        Key=store.spot_key(run_id, "s1"),
        UpdateExpression="SET processing_status=:status",
        ExpressionAttributeValues={":status": "in_progress"},
    )

    def fail_transaction(**kwargs):
        raise AssertionError("mark_processing_terminal should not call TransactWriteItems")

    monkeypatch.setattr(store.dynamodb.meta.client, "transact_write_items", fail_transaction)

    assert (
        store.mark_processing_terminal(
            forecast_run_id=run_id,
            spot_id="s1",
            processing_status="success",
        )
        is True
    )

    run = table.get_item(Key=store.run_key(run_id))["Item"]
    spot = table.get_item(Key=store.spot_key(run_id, "s1"))["Item"]
    assert spot["processing_status"] == "success"
    assert run["terminal_processing_count"] == 1
    assert run["successful_processing_count"] == 1


@mock_aws
def test_scrape_terminal_run_counter_failure_leaves_spot_terminal_but_counter_unchanged(monkeypatch):
    dynamodb, table = create_table()
    store = ForecastControlStore(table_name="forecast-control-test", dynamodb_resource=dynamodb)
    run_id = "forecast#offset=-10#scrape_date=2026-05-22#time=04-00"
    store.create_run_if_absent(
        forecast_run_id=run_id,
        scrape_date="2026-05-22",
        scheduled_utc_time="2026-05-22T14:00:00+00:00",
        local_scrape_time="04:00",
        local_date="2026-05-22",
        utc_offset=-10,
        expected_scrape_count=1,
    )
    store.seed_spots(forecast_run_id=run_id, spots=[{"spot_id": "s1", "spot_version_id": "v1"}])
    original_update_item = store.table.update_item
    call_count = 0

    def fail_second_update(**kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 2:
            raise ClientError(
                {"Error": {"Code": "ProvisionedThroughputExceededException", "Message": "throttled"}},
                "UpdateItem",
            )
        return original_update_item(**kwargs)

    monkeypatch.setattr(store.table, "update_item", fail_second_update)

    with pytest.raises(ClientError):
        store.record_scrape_terminal(
            forecast_run_id=run_id,
            spot_id="s1",
            scrape_status="success",
            raw_bucket="bucket",
            raw_key="key.json.gz",
        )

    run = table.get_item(Key=store.run_key(run_id))["Item"]
    spot = table.get_item(Key=store.spot_key(run_id, "s1"))["Item"]
    assert spot["scrape_status"] == "success"
    assert spot["raw_key"] == "key.json.gz"
    assert run["terminal_scrape_count"] == 0
    assert run["successful_scrape_count"] == 0
    assert run["expected_processing_count"] == 0


@mock_aws
def test_in_progress_processing_claim_is_not_reclaimed_until_after_six_minutes(monkeypatch):
    dynamodb, table = create_table()
    store = ForecastControlStore(table_name="forecast-control-test", dynamodb_resource=dynamodb)
    run_id = "forecast#offset=-10#scrape_date=2026-05-22#time=04-00"
    store.seed_spots(forecast_run_id=run_id, spots=[{"spot_id": "s1", "spot_version_id": "v1"}])
    table.update_item(
        Key=store.spot_key(run_id, "s1"),
        UpdateExpression="SET processing_status=:status, processing_claimed_at=:claimed_at",
        ExpressionAttributeValues={
            ":status": "in_progress",
            ":claimed_at": (datetime.now(timezone.utc) - timedelta(seconds=330)).isoformat(),
        },
    )

    assert store.claim_processing(forecast_run_id=run_id, spot_id="s1") is False

    table.update_item(
        Key=store.spot_key(run_id, "s1"),
        UpdateExpression="SET processing_claimed_at=:claimed_at",
        ExpressionAttributeValues={
            ":claimed_at": (datetime.now(timezone.utc) - timedelta(seconds=370)).isoformat(),
        },
    )

    assert store.claim_processing(forecast_run_id=run_id, spot_id="s1") is True


@mock_aws
def test_claim_processing_and_mark_success_increment_processing_once(monkeypatch):
    dynamodb, table = create_table()
    store = ForecastControlStore(table_name="forecast-control-test", dynamodb_resource=dynamodb)
    run_id = "forecast#offset=-10#scrape_date=2026-05-22#time=04-00"
    store.create_run_if_absent(
        forecast_run_id=run_id,
        scrape_date="2026-05-22",
        scheduled_utc_time="2026-05-22T14:00:00+00:00",
        local_scrape_time="04:00",
        local_date="2026-05-22",
        utc_offset=-10,
        expected_scrape_count=1,
    )
    store.seed_spots(forecast_run_id=run_id, spots=[{"spot_id": "s1", "spot_version_id": "v1"}])
    store.record_scrape_terminal(forecast_run_id=run_id, spot_id="s1", scrape_status="success")

    assert store.claim_processing(forecast_run_id=run_id, spot_id="s1") is True
    assert store.claim_processing(forecast_run_id=run_id, spot_id="s1") is False
    assert (
        store.mark_processing_terminal(
            forecast_run_id=run_id, spot_id="s1", processing_status="success"
        )
        is True
    )
    assert (
        store.mark_processing_terminal(
            forecast_run_id=run_id, spot_id="s1", processing_status="success"
        )
        is False
    )
    store.update_run_rollup(run_id)

    run = table.get_item(Key=store.run_key(run_id))["Item"]
    assert run["terminal_processing_count"] == 1
    assert run["successful_processing_count"] == 1
    assert run["scrape_status"] == "complete"
    assert run["processing_status"] == "complete"
    assert run["status"] == "complete"


@mock_aws
def test_failed_scrape_counts_once_and_run_completes_with_scrape_failures(monkeypatch):
    dynamodb, table = create_table()
    store = ForecastControlStore(table_name="forecast-control-test", dynamodb_resource=dynamodb)
    run_id = "forecast#offset=-10#scrape_date=2026-05-22#time=04-00"
    store.create_run_if_absent(
        forecast_run_id=run_id,
        scrape_date="2026-05-22",
        scheduled_utc_time="2026-05-22T14:00:00+00:00",
        local_scrape_time="04:00",
        local_date="2026-05-22",
        utc_offset=-10,
        expected_scrape_count=1,
    )
    store.seed_spots(forecast_run_id=run_id, spots=[{"spot_id": "s1", "spot_version_id": "v1"}])

    assert (
        store.record_scrape_terminal(
            forecast_run_id=run_id,
            spot_id="s1",
            scrape_status="failed",
            failure_source="fetch",
            failure_reason="timeout",
        )
        is True
    )
    assert (
        store.record_scrape_terminal(
            forecast_run_id=run_id,
            spot_id="s1",
            scrape_status="failed",
            failure_source="fetch",
            failure_reason="timeout",
        )
        is False
    )
    store.update_run_rollup(run_id)

    run = table.get_item(Key=store.run_key(run_id))["Item"]
    spot = table.get_item(Key=store.spot_key(run_id, "s1"))["Item"]
    assert spot["scrape_failure_source"] == "fetch"
    assert run["terminal_scrape_count"] == 1
    assert run["failed_scrape_count"] == 1
    assert run["expected_processing_count"] == 0
    assert run["scrape_status"] == "complete_with_failures"
    assert run["processing_status"] == "complete"
    assert run["status"] == "complete"


@mock_aws
def test_processing_failure_counts_once_and_run_completes_with_processing_failures(monkeypatch):
    dynamodb, table = create_table()
    store = ForecastControlStore(table_name="forecast-control-test", dynamodb_resource=dynamodb)
    run_id = "forecast#offset=-10#scrape_date=2026-05-22#time=04-00"
    store.create_run_if_absent(
        forecast_run_id=run_id,
        scrape_date="2026-05-22",
        scheduled_utc_time="2026-05-22T14:00:00+00:00",
        local_scrape_time="04:00",
        local_date="2026-05-22",
        utc_offset=-10,
        expected_scrape_count=1,
    )
    store.seed_spots(forecast_run_id=run_id, spots=[{"spot_id": "s1", "spot_version_id": "v1"}])
    store.record_scrape_terminal(forecast_run_id=run_id, spot_id="s1", scrape_status="success")
    assert store.claim_processing(forecast_run_id=run_id, spot_id="s1") is True

    assert (
        store.mark_processing_terminal(
            forecast_run_id=run_id,
            spot_id="s1",
            processing_status="failed",
            failure_source="postgres",
            failure_reason="boom",
        )
        is True
    )
    assert (
        store.mark_processing_terminal(
            forecast_run_id=run_id,
            spot_id="s1",
            processing_status="failed",
            failure_source="postgres",
            failure_reason="boom",
        )
        is False
    )
    store.update_run_rollup(run_id)

    run = table.get_item(Key=store.run_key(run_id))["Item"]
    spot = table.get_item(Key=store.spot_key(run_id, "s1"))["Item"]
    assert spot["processing_failure_source"] == "postgres"
    assert run["terminal_processing_count"] == 1
    assert run["failed_processing_count"] == 1
    assert run["scrape_status"] == "complete"
    assert run["processing_status"] == "complete_with_failures"
    assert run["status"] == "complete"
