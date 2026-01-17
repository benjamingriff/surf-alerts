import os
import logging
import boto3
import pytest
from moto import mock_aws

AWS_REGION = "eu-west-2"
JOB_ID = "12345"


@pytest.fixture(scope="session", autouse=True)
def test_logging():
    logging.getLogger("botocore").setLevel("WARNING")
    logging.getLogger("boto3").setLevel("WARNING")
    logging.getLogger("httpcore").setLevel("WARNING")
    yield


@pytest.fixture(scope="session", autouse=True)
def aws_env():
    os.environ["AWS_ACCESS_KEY_ID"] = "testing"
    os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
    os.environ["AWS_DEFAULT_REGION"] = AWS_REGION
    os.environ["JOB_ID"] = JOB_ID
    os.environ["S3_BUCKET_NAME"] = "dataeng-squeegee-test-bucket"
    os.environ["JOB_TABLE_NAME"] = "dataeng-squeegee-test-job-table"
    os.environ["SQS_QUEUE_NAME"] = "dataeng-squeegee-test-queue"
    os.environ["QUEUE_REGISTRY_PREFIX"] = "/dataeng-squeegee-test/scrapers"
    os.environ["RS_SECRET_NAME"] = "redshift-creds-test"
    yield


@pytest.fixture(scope="function", autouse=True)
def s3():
    with mock_aws():
        s3_client = boto3.client("s3", region_name=AWS_REGION)
        s3_client.create_bucket(
            Bucket=os.environ["S3_BUCKET_NAME"],
            CreateBucketConfiguration={"LocationConstraint": AWS_REGION},
        )
        yield s3_client
