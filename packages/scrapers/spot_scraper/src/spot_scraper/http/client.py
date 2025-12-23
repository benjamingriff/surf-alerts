import random
import time

from curl_cffi import requests

from spot_scraper.logger import get_logger

HEADERS = {
    "Accept": "application/json",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.surfline.com/",
    "Origin": "https://www.surfline.com",
}

IMPERSONATOR = "chrome"

logger = get_logger()


def make_request(
    url: str,
    max_retries: int = 3,
) -> requests.Response:
    attempt = 0
    backoff = 1.0
    timeout_seconds = 30.0

    headers = HEADERS
    impersonate = IMPERSONATOR
    resp = None

    while attempt < max_retries:
        attempt += 1
        try:
            logger.debug(
                "curl_cffi_request_start",
                extra={
                    "url": url,
                    "attempt": attempt,
                    "max_retries": max_retries,
                    "impersonate": impersonate,
                },
            )

            resp = requests.get(
                url,
                headers=headers,
                impersonate=impersonate,
                timeout=timeout_seconds,
            )

            resp.raise_for_status()

            logger.debug(
                "curl_cffi_request_success",
                extra={
                    "url": url,
                    "attempt": attempt,
                    "status_code": resp.status_code,
                    "elapsed_ms": int(getattr(resp, "elapsed", 0) * 1000)
                    if isinstance(getattr(resp, "elapsed", None), (int, float))
                    else None,
                },
            )
            return resp

        except Exception as e:
            status_code = getattr(getattr(e, "response", None), "status_code", None)
            response_headers = getattr(getattr(e, "response", None), "headers", None)
            response_text = getattr(getattr(e, "response", None), "text", None)

            is_429 = status_code == 429 or getattr(resp, "status_code", None) == 429

            if attempt < max_retries:
                jitter = random.uniform(0.0, 1.0)
                wait_time = backoff + jitter

                logger.warning(
                    "curl_cffi_request_retry",
                    extra={
                        "url": url,
                        "attempt": attempt,
                        "max_retries": max_retries,
                        "status_code": status_code
                        or getattr(resp, "status_code", None),
                        "impersonate": impersonate,
                        "error": str(e),
                        "wait_seconds": wait_time,
                        "rate_limited": is_429,
                        "response_headers": response_headers,
                        "response_text": response_text[:5000]
                        if isinstance(response_text, str)
                        else None,
                    },
                )

                time.sleep(wait_time)
                backoff *= 2.0
                continue

            logger.error(
                "curl_cffi_request_failed",
                extra={
                    "url": url,
                    "attempt": attempt,
                    "max_retries": max_retries,
                    "status_code": status_code or getattr(resp, "status_code", None),
                    "impersonate": impersonate,
                    "error": str(e),
                },
                exc_info=True,
            )
            raise
