import json

import boto3

from discovery_failure_finalizer.handler import lambda_handler


def test_failure_finalizer_enqueues_failed_completion(monkeypatch, lambda_context):
    sqs_client = boto3.client("sqs", region_name="eu-west-2")
    completion_queue_url = sqs_client.create_queue(QueueName="completion-queue")["QueueUrl"]
    monkeypatch.setenv("DISCOVERY_COMPLETION_QUEUE_URL", completion_queue_url)

    response = lambda_handler(
        {
            "Records": [
                {
                    "body": json.dumps(
                        {
                            "spot_id": "abc",
                            "discovery_run_id": "run-1",
                        }
                    )
                }
            ]
        },
        lambda_context,
    )

    assert response["statusCode"] == 200
    message = sqs_client.receive_message(QueueUrl=completion_queue_url, MaxNumberOfMessages=1)["Messages"][0]
    payload = json.loads(message["Body"])
    assert payload["spot_id"] == "abc"
    assert payload["discovery_run_id"] == "run-1"
    assert payload["terminal_status"] == "failed"
