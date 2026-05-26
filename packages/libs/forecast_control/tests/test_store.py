import boto3
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
