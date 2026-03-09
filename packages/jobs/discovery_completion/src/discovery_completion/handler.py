import re
from datetime import datetime, timezone
from urllib.parse import unquote_plus

from aws_lambda_powertools.utilities.typing import LambdaContext

from discovery_completion.logger import get_logger, inject_lambda_context
from discovery_completion.s3 import S3Client

logger = get_logger()
s3_client = S3Client()
SCHEMA_VERSION = 1

RUN_KEY_PATTERN = re.compile(
    r"control/manifests/discovery_runs/date=(?P<scrape_date>\d{4}-\d{2}-\d{2})/"
    r"run_id=(?P<run_id>[^/]+)"
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_s3_reference(event: dict) -> tuple[str, str]:
    if "detail" in event:
        return event["detail"]["bucket"]["name"], unquote_plus(event["detail"]["object"]["key"])

    record = event["Records"][0]
    return record["s3"]["bucket"]["name"], unquote_plus(record["s3"]["object"]["key"])


def _extract_run_context(key: str) -> tuple[str, str]:
    match = RUN_KEY_PATTERN.search(key)
    if not match:
        raise ValueError(f"Could not derive discovery run context from key: {key}")
    return match.group("scrape_date"), match.group("run_id")


def _manifest_key(scrape_date: str, run_id: str) -> str:
    return f"control/manifests/discovery_runs/date={scrape_date}/run_id={run_id}.json.gz"


def _completion_prefix(scrape_date: str, run_id: str) -> str:
    return f"control/manifests/discovery_runs/date={scrape_date}/run_id={run_id}/completed/"


@inject_lambda_context(log_event=False)
def lambda_handler(event: dict, context: LambdaContext):
    bucket, key = _parse_s3_reference(event)
    scrape_date, run_id = _extract_run_context(key)
    manifest_key = _manifest_key(scrape_date, run_id)
    manifest = s3_client.get_json(bucket, manifest_key)
    if manifest is None:
        raise FileNotFoundError(f"Missing discovery manifest: s3://{bucket}/{manifest_key}")

    processing_manifest_key = manifest["processing_manifest_key"]
    if s3_client.object_exists(bucket, processing_manifest_key):
        logger.info("Processing manifest already exists", extra={"processing_manifest_key": processing_manifest_key})
        return {"statusCode": 200, "body": "duplicate completion event ignored"}

    completion_keys = [
        completion_key
        for completion_key in s3_client.list_keys(bucket, _completion_prefix(scrape_date, run_id))
        if completion_key.endswith(".json.gz")
    ]
    if len(completion_keys) < manifest["expected_count"]:
        logger.info(
            "Discovery run not complete yet",
            extra={"completed_count": len(completion_keys), "expected_count": manifest["expected_count"]},
        )
        return {"statusCode": 200, "body": "waiting for remaining spot reports"}

    completion_payloads = [s3_client.get_json(bucket, completion_key) for completion_key in completion_keys]
    source_keys = [manifest["sitemap_raw_key"]]
    source_keys.extend(payload["raw_key"] for payload in completion_payloads if payload)
    s3_client.put_json(
        bucket,
        processing_manifest_key,
        {
            "schema_version": SCHEMA_VERSION,
            "domain": "discovery",
            "discovery_run_id": run_id,
            "scrape_date": scrape_date,
            "source_manifest_key": manifest_key,
            "source_keys": source_keys,
            "ready_at": _utc_now().isoformat(),
        },
    )
    return {"statusCode": 200, "body": "processing manifest emitted"}
