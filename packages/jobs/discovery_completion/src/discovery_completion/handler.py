import re
from datetime import datetime, timezone
from urllib.parse import unquote_plus

from aws_lambda_powertools.utilities.typing import LambdaContext

from discovery_completion.logger import get_logger, inject_lambda_context
from discovery_completion.s3 import S3Client

logger = get_logger()
s3_client = S3Client()
SCHEMA_VERSION = 1

COMPLETION_KEY_PATTERN = re.compile(
    r"control/completions/discovery_spot_scrapes(?:_failed)?/date=(?P<scrape_date>\d{4}-\d{2}-\d{2})/"
    r"discovery_run_id=(?P<discovery_run_id>[^/]+)/spot_id=(?P<spot_id>[^/]+)\.json\.gz$"
)
SUCCESS_COMPLETION_PREFIX = "control/completions/discovery_spot_scrapes"
FAILED_COMPLETION_PREFIX = "control/completions/discovery_spot_scrapes_failed"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_s3_reference(event: dict) -> tuple[str, str]:
    if "detail" in event:
        return event["detail"]["bucket"]["name"], unquote_plus(event["detail"]["object"]["key"])

    record = event["Records"][0]
    return record["s3"]["bucket"]["name"], unquote_plus(record["s3"]["object"]["key"])


def _extract_run_context(key: str) -> tuple[str, str]:
    match = COMPLETION_KEY_PATTERN.search(key)
    if not match:
        raise ValueError(f"Could not derive discovery run context from key: {key}")
    return match.group("scrape_date"), match.group("discovery_run_id")


def _discovery_manifest_key(scrape_date: str, discovery_run_id: str) -> str:
    return (
        "control/manifests/discovery_runs/"
        f"date={scrape_date}/discovery_run_id={discovery_run_id}/manifest.json.gz"
    )


def _completion_prefix(prefix_root: str, scrape_date: str, discovery_run_id: str) -> str:
    return f"{prefix_root}/date={scrape_date}/discovery_run_id={discovery_run_id}/"


def _load_terminal_markers(bucket: str, scrape_date: str, discovery_run_id: str) -> tuple[dict, dict]:
    success_keys = [
        key
        for key in s3_client.list_keys(bucket, _completion_prefix(SUCCESS_COMPLETION_PREFIX, scrape_date, discovery_run_id))
        if key.endswith(".json.gz")
    ]
    failed_keys = [
        key
        for key in s3_client.list_keys(bucket, _completion_prefix(FAILED_COMPLETION_PREFIX, scrape_date, discovery_run_id))
        if key.endswith(".json.gz")
    ]

    success_payloads = [s3_client.get_json(bucket, key) for key in success_keys]
    failed_payloads = [s3_client.get_json(bucket, key) for key in failed_keys]
    successes_by_spot_id = {
        payload["spot_id"]: payload
        for payload in success_payloads
        if payload and payload.get("spot_id")
    }
    failures_by_spot_id = {
        payload["spot_id"]: payload
        for payload in failed_payloads
        if payload and payload.get("spot_id") and payload["spot_id"] not in successes_by_spot_id
    }
    return successes_by_spot_id, failures_by_spot_id


def _processing_manifest_key(scrape_date: str, discovery_run_id: str) -> str:
    return (
        "control/manifests/processing/"
        f"domain=discovery/stage=spot_history/date={scrape_date}/discovery_run_id={discovery_run_id}.json.gz"
    )


@inject_lambda_context(log_event=False)
def lambda_handler(event: dict, context: LambdaContext):
    bucket, key = _parse_s3_reference(event)
    scrape_date, discovery_run_id = _extract_run_context(key)
    manifest_key = _discovery_manifest_key(scrape_date, discovery_run_id)
    manifest = s3_client.get_json(bucket, manifest_key)
    if manifest is None:
        raise FileNotFoundError(f"Missing discovery manifest: s3://{bucket}/{manifest_key}")

    processing_manifest_key = _processing_manifest_key(scrape_date, discovery_run_id)
    if s3_client.object_exists(bucket, processing_manifest_key):
        logger.info("Processing manifest already exists", extra={"processing_manifest_key": processing_manifest_key})
        return {"statusCode": 200, "body": "duplicate completion event ignored"}

    expected_count = manifest["added_spot_count"]

    success_count = s3_client.count_keys(
        bucket, _completion_prefix(SUCCESS_COMPLETION_PREFIX, scrape_date, discovery_run_id), suffix=".json.gz"
    )
    failed_count = s3_client.count_keys(
        bucket, _completion_prefix(FAILED_COMPLETION_PREFIX, scrape_date, discovery_run_id), suffix=".json.gz"
    )
    terminal_count = success_count + failed_count

    if terminal_count < expected_count:
        logger.info(
            "Discovery run not complete yet",
            extra={
                "successful_count": success_count,
                "failed_count": failed_count,
                "terminal_count": terminal_count,
                "expected_count": expected_count,
            },
        )
        return {"statusCode": 200, "body": "waiting for remaining spot scrapes"}

    successes_by_spot_id, failures_by_spot_id = _load_terminal_markers(bucket, scrape_date, discovery_run_id)

    ordered_spot_ids = [spot_id for spot_id in manifest["added_spot_ids"] if spot_id in successes_by_spot_id]
    raw_keys = [successes_by_spot_id[spot_id]["raw_key"] for spot_id in ordered_spot_ids]
    failed_spot_ids = [spot_id for spot_id in manifest["added_spot_ids"] if spot_id in failures_by_spot_id]
    failed_spots = [
        {
            "spot_id": spot_id,
            "failure_reason": failures_by_spot_id[spot_id].get("failure_reason"),
            "failure_source": failures_by_spot_id[spot_id].get("failure_source"),
            "completed_at": failures_by_spot_id[spot_id].get("completed_at"),
        }
        for spot_id in failed_spot_ids
    ]
    s3_client.put_json(
        bucket,
        processing_manifest_key,
        {
            "schema_version": SCHEMA_VERSION,
            "manifest_type": "processing_manifest",
            "domain": "discovery",
            "stage": "spot_history",
            "discovery_run_id": discovery_run_id,
            "scrape_date": scrape_date,
            "source_manifest_key": manifest_key,
            "spot_ids": ordered_spot_ids,
            "raw_keys": raw_keys,
            "failed_spot_ids": failed_spot_ids,
            "failed_spot_count": len(failed_spot_ids),
            "failed_spots": failed_spots,
            "ready_at": _utc_now().isoformat(),
        },
    )
    return {"statusCode": 200, "body": "spot history manifest emitted"}
