from datetime import datetime, timedelta, timezone

import boto3
import pytest
from boto3.dynamodb.types import TypeDeserializer
from botocore.exceptions import ClientError
from moto import mock_aws

from forecast_control.store import ForecastControlStore

_DESERIALIZER = TypeDeserializer()


def _native_values(values):
    return {key: _DESERIALIZER.deserialize(value) for key, value in values.items()}


def install_transaction_stub(store, table, monkeypatch):
    def transact_write_items(**kwargs):
        # Moto currently accepts resource-style native values for transact_write_items but
        # fails on real client AttributeValue payloads, so these tests emulate the
        # transaction against moto using Table.update_item while preserving conditional
        # duplicate behavior.
        for item in kwargs["TransactItems"]:
            update = item["Update"]
            key = _native_values(update["Key"])
            values = _native_values(update["ExpressionAttributeValues"])
            condition = update.get("ConditionExpression")
            existing = table.get_item(Key=key).get("Item", {})
            if condition == "scrape_status IN (:planned, :in_progress)" and existing.get(
                "scrape_status"
            ) not in {values[":planned"], values[":in_progress"]}:
                raise ClientError(
                    {
                        "Error": {"Code": "TransactionCanceledException"},
                        "CancellationReasons": [{"Code": "ConditionalCheckFailed"}],
                    },
                    "TransactWriteItems",
                )
            if (
                condition == "processing_status=:in_progress"
                and existing.get("processing_status") != values[":in_progress"]
            ):
                raise ClientError(
                    {
                        "Error": {"Code": "TransactionCanceledException"},
                        "CancellationReasons": [{"Code": "ConditionalCheckFailed"}],
                    },
                    "TransactWriteItems",
                )
        for item in kwargs["TransactItems"]:
            update = item["Update"]
            expression = update["UpdateExpression"]
            values = _native_values(update["ExpressionAttributeValues"])
            table.update_item(
                Key=_native_values(update["Key"]),
                UpdateExpression=expression,
                ExpressionAttributeValues={
                    key: value for key, value in values.items() if key in expression
                },
            )
        return {}

    monkeypatch.setattr(store.dynamodb.meta.client, "transact_write_items", transact_write_items)


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
def test_seed_spots_can_overwrite_on_initial_planning_and_get_run_reads_by_run_key():
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

    run = store.get_run(run_id)
    spot = table.get_item(Key=store.spot_key(run_id, "s1"))["Item"]
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
    install_transaction_stub(store, table, monkeypatch)

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
@mock_aws
def test_record_scrape_terminal_transaction_uses_client_attribute_value_payload(monkeypatch):
    dynamodb, _table = create_table()
    store = ForecastControlStore(table_name="forecast-control-test", dynamodb_resource=dynamodb)
    captured = {}

    def capture_transaction(**kwargs):
        captured.update(kwargs)
        return {}

    monkeypatch.setattr(store.dynamodb.meta.client, "transact_write_items", capture_transaction)

    assert (
        store.record_scrape_terminal(
            forecast_run_id="run-1",
            spot_id="s1",
            scrape_status="success",
            raw_bucket="bucket",
            raw_key="key.json.gz",
            scraped_at="2026-05-22T14:01:00+00:00",
        )
        is True
    )

    spot_update = captured["TransactItems"][0]["Update"]
    run_update = captured["TransactItems"][1]["Update"]
    assert spot_update["Key"] == {
        "pk": {"S": "FORECAST_RUN#run-1"},
        "sk": {"S": "SPOT#s1"},
    }
    assert spot_update["ExpressionAttributeValues"][":status"] == {"S": "success"}
    assert spot_update["ExpressionAttributeValues"][":ttl"]["N"].isdigit()
    assert run_update["Key"] == {"pk": {"S": "FORECAST_RUN#run-1"}, "sk": {"S": "RUN"}}
    assert run_update["ExpressionAttributeValues"][":one"] == {"N": "1"}


@mock_aws
@mock_aws
def test_transaction_canceled_without_conditional_reason_raises(monkeypatch):
    dynamodb, _table = create_table()
    store = ForecastControlStore(table_name="forecast-control-test", dynamodb_resource=dynamodb)

    def cancel_without_reasons(**kwargs):
        raise ClientError(
            {"Error": {"Code": "TransactionCanceledException", "Message": "cancelled"}},
            "TransactWriteItems",
        )

    monkeypatch.setattr(store.dynamodb.meta.client, "transact_write_items", cancel_without_reasons)

    with pytest.raises(ClientError):
        store.record_scrape_terminal(
            forecast_run_id="run-1",
            spot_id="s1",
            scrape_status="success",
        )


@mock_aws
def test_scrape_terminal_transaction_failure_leaves_spot_and_run_counters_unchanged(monkeypatch):
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
        raise ClientError(
            {"Error": {"Code": "ProvisionedThroughputExceededException", "Message": "throttled"}},
            "TransactWriteItems",
        )

    monkeypatch.setattr(store.dynamodb.meta.client, "transact_write_items", fail_transaction)

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
    assert spot["scrape_status"] == "planned"
    assert "raw_key" not in spot
    assert run["terminal_scrape_count"] == 0
    assert run["successful_scrape_count"] == 0
    assert run["expected_processing_count"] == 0


@mock_aws
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
    install_transaction_stub(store, table, monkeypatch)
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
