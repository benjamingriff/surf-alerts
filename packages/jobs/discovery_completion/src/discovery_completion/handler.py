import re
import time
from datetime import datetime, timezone
from urllib.parse import unquote_plus

from aws_lambda_powertools.utilities.typing import LambdaContext

from discovery_completion.logger import get_logger, inject_lambda_context
from discovery_completion.s3 import S3Client

logger = get_logger()
s3_client = S3Client()
SCHEMA_VERSION = 1

RUN_CONTEXT_PATTERN = re.compile(
    r"control/completions/discovery_spot_scrapes(?:_failed)?/date=(?P<scrape_date>\d{4}-\d{2}-\d{2})/"
    r"discovery_run_id=(?P<discovery_run_id>[^/]+)/"
)
SUCCESS_COMPLETION_KEY_PATTERN = re.compile(
    r"control/completions/discovery_spot_scrapes/date=(?P<scrape_date>\d{4}-\d{2}-\d{2})/"
    r"discovery_run_id=(?P<discovery_run_id>[^/]+)/spot_id=(?P<spot_id>[^/]+)/"
    r"raw_run_id=(?P<raw_run_id>[^/]+)\.json\.gz$"
)
LEGACY_SUCCESS_COMPLETION_KEY_PATTERN = re.compile(
    r"control/completions/discovery_spot_scrapes/date=(?P<scrape_date>\d{4}-\d{2}-\d{2})/"
    r"discovery_run_id=(?P<discovery_run_id>[^/]+)/spot_id=(?P<spot_id>[^/]+)\.json\.gz$"
)
FAILED_COMPLETION_KEY_PATTERN = re.compile(
    r"control/completions/discovery_spot_scrapes_failed/date=(?P<scrape_date>\d{4}-\d{2}-\d{2})/"
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
    match = RUN_CONTEXT_PATTERN.search(key)
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


def _raw_report_key(scrape_date: str, spot_id: str, raw_run_id: str) -> str:
    return f"raw/spot_report/spot_id={spot_id}/scrape_date={scrape_date}/run_id={raw_run_id}.json.gz"


def _scan_success_markers(bucket: str, scrape_date: str, discovery_run_id: str) -> tuple[int, dict[str, str], list[str]]:
    success_count = 0
    raw_keys_by_spot_id: dict[str, str] = {}
    legacy_success_keys: list[str] = []
    prefix = _completion_prefix(SUCCESS_COMPLETION_PREFIX, scrape_date, discovery_run_id)

    for key in s3_client.list_keys(bucket, prefix):
        match = SUCCESS_COMPLETION_KEY_PATTERN.search(key)
        if match:
            success_count += 1
            raw_keys_by_spot_id[match.group("spot_id")] = _raw_report_key(
                scrape_date=scrape_date,
                spot_id=match.group("spot_id"),
                raw_run_id=match.group("raw_run_id"),
            )
            continue

        legacy_match = LEGACY_SUCCESS_COMPLETION_KEY_PATTERN.search(key)
        if legacy_match:
            success_count += 1
            legacy_success_keys.append(key)

    return success_count, raw_keys_by_spot_id, legacy_success_keys


def _scan_failure_markers(bucket: str, scrape_date: str, discovery_run_id: str) -> tuple[int, list[str]]:
    failed_keys: list[str] = []
    prefix = _completion_prefix(FAILED_COMPLETION_PREFIX, scrape_date, discovery_run_id)

    for key in s3_client.list_keys(bucket, prefix):
        if FAILED_COMPLETION_KEY_PATTERN.search(key):
            failed_keys.append(key)

    return len(failed_keys), failed_keys


def _load_legacy_success_markers(bucket: str, keys: list[str]) -> dict[str, str]:
    raw_keys_by_spot_id: dict[str, str] = {}
    for key in keys:
        payload = s3_client.get_json(bucket, key)
        if payload and payload.get("spot_id") and payload.get("raw_key"):
            raw_keys_by_spot_id[payload["spot_id"]] = payload["raw_key"]
    return raw_keys_by_spot_id


def _load_failure_markers(bucket: str, keys: list[str]) -> dict[str, dict]:
    failures_by_spot_id: dict[str, dict] = {}
    for key in keys:
        payload = s3_client.get_json(bucket, key)
        if payload and payload.get("spot_id"):
            failures_by_spot_id[payload["spot_id"]] = payload
    return failures_by_spot_id


def _processing_manifest_key(scrape_date: str, discovery_run_id: str) -> str:
    return (
        "control/manifests/processing/"
        f"domain=discovery/stage=spot_history/date={scrape_date}/discovery_run_id={discovery_run_id}.json.gz"
    )


@inject_lambda_context(log_event=False)
def lambda_handler(event: dict, context: LambdaContext):
    handler_start = time.perf_counter()
    bucket, key = _parse_s3_reference(event)
    scrape_date, discovery_run_id = _extract_run_context(key)
    manifest_key = _discovery_manifest_key(scrape_date, discovery_run_id)

    manifest_start = time.perf_counter()
    manifest = s3_client.get_json(bucket, manifest_key)
    manifest_load_ms = round((time.perf_counter() - manifest_start) * 1000, 2)
    if manifest is None:
        raise FileNotFoundError(f"Missing discovery manifest: s3://{bucket}/{manifest_key}")

    processing_manifest_key = _processing_manifest_key(scrape_date, discovery_run_id)
    if s3_client.object_exists(bucket, processing_manifest_key):
        logger.info("Processing manifest already exists", extra={"processing_manifest_key": processing_manifest_key})
        return {"statusCode": 200, "body": "duplicate completion event ignored"}

    expected_count = manifest["added_spot_count"]

    success_scan_start = time.perf_counter()
    success_count, raw_keys_by_spot_id, legacy_success_keys = _scan_success_markers(
        bucket,
        scrape_date,
        discovery_run_id,
    )
    success_scan_ms = round((time.perf_counter() - success_scan_start) * 1000, 2)

    failure_scan_start = time.perf_counter()
    failed_count, failed_keys = _scan_failure_markers(bucket, scrape_date, discovery_run_id)
    failure_scan_ms = round((time.perf_counter() - failure_scan_start) * 1000, 2)

    terminal_count = success_count + failed_count
    scan_metrics = {
        "manifest_load_ms": manifest_load_ms,
        "success_scan_ms": success_scan_ms,
        "failure_scan_ms": failure_scan_ms,
        "successful_count": success_count,
        "failed_count": failed_count,
        "terminal_count": terminal_count,
        "expected_count": expected_count,
        "legacy_success_marker_count": len(legacy_success_keys),
        "failed_marker_count": len(failed_keys),
        "handler_elapsed_ms": round((time.perf_counter() - handler_start) * 1000, 2),
    }

    if terminal_count < expected_count:
        logger.info("Discovery run not complete yet", extra=scan_metrics)
        return {"statusCode": 200, "body": "waiting for remaining spot scrapes"}

    legacy_load_start = time.perf_counter()
    raw_keys_by_spot_id.update(_load_legacy_success_markers(bucket, legacy_success_keys))
    legacy_success_load_ms = round((time.perf_counter() - legacy_load_start) * 1000, 2)

    failure_load_start = time.perf_counter()
    failures_by_spot_id = _load_failure_markers(bucket, failed_keys)
    failure_load_ms = round((time.perf_counter() - failure_load_start) * 1000, 2)

    ordered_spot_ids = [spot_id for spot_id in manifest["added_spot_ids"] if spot_id in raw_keys_by_spot_id]
    raw_keys = [raw_keys_by_spot_id[spot_id] for spot_id in ordered_spot_ids]
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

    manifest_write_start = time.perf_counter()
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
    logger.info(
        "Discovery spot history manifest emitted",
        extra={
            **scan_metrics,
            "legacy_success_load_ms": legacy_success_load_ms,
            "failure_load_ms": failure_load_ms,
            "manifest_write_ms": round((time.perf_counter() - manifest_write_start) * 1000, 2),
            "handler_elapsed_ms": round((time.perf_counter() - handler_start) * 1000, 2),
        },
    )
    return {"statusCode": 200, "body": "spot history manifest emitted"}
