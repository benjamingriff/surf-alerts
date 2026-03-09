import os
import logging
import sys
from pathlib import Path
from types import SimpleNamespace

import boto3
import pytest
from moto import mock_aws

AWS_REGION = "eu-west-2"
JOB_ID = "12345"
REPO_ROOT = Path(__file__).resolve().parent
SRC_PATHS = [
    REPO_ROOT / "packages" / "jobs" / "discovery_catalog_builder" / "src",
    REPO_ROOT / "packages" / "jobs" / "discovery_completion" / "src",
    REPO_ROOT / "packages" / "jobs" / "discovery_diff" / "src",
    REPO_ROOT / "packages" / "jobs" / "discovery_failure_finalizer" / "src",
    REPO_ROOT / "packages" / "jobs" / "discovery_spot_history_processor" / "src",
    REPO_ROOT / "packages" / "jobs" / "spot_reconciler" / "src",
    REPO_ROOT / "packages" / "scrapers" / "forecast_scraper" / "src",
    REPO_ROOT / "packages" / "scrapers" / "sitemap_scraper" / "src",
    REPO_ROOT / "packages" / "scrapers" / "spot_scraper" / "src",
    REPO_ROOT / "packages" / "scrapers" / "taxonomy_scraper" / "src",
]

for src_path in SRC_PATHS:
    sys.path.insert(0, str(src_path))


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


@pytest.fixture
def lambda_context():
    return SimpleNamespace(
        function_name="test-function",
        function_version="$LATEST",
        invoked_function_arn="arn:aws:lambda:eu-west-2:123456789012:function:test-function",
        memory_limit_in_mb=256,
        aws_request_id="test-request-id",
    )
