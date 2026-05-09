"""Polite HTTP client for fwc.gov.au."""

from __future__ import annotations

import time
from typing import Any

import httpx

USER_AGENT = "fwc-super-research/0.1 (+contact: timba2000@gmail.com)"
BASE_URL = "https://www.fwc.gov.au"
DEFAULT_DELAY = 1.0  # seconds between requests


class PoliteClient:
    """httpx client with built-in throttling, retries, and backoff."""

    def __init__(self, delay: float = DEFAULT_DELAY, timeout: float = 30.0):
        self._delay = delay
        self._last_call = 0.0
        self._client = httpx.Client(
            base_url=BASE_URL,
            http2=True,
            timeout=timeout,
            headers={"User-Agent": USER_AGENT, "Accept-Language": "en-AU,en;q=0.9"},
            follow_redirects=True,
        )

    def _throttle(self) -> None:
        now = time.monotonic()
        wait = self._delay - (now - self._last_call)
        if wait > 0:
            time.sleep(wait)
        self._last_call = time.monotonic()

    def get(self, path: str, *, max_retries: int = 4, **kwargs: Any) -> httpx.Response:
        self._throttle()
        attempt = 0
        while True:
            try:
                resp = self._client.get(path, **kwargs)
                if resp.status_code == 429:
                    retry = float(resp.headers.get("Retry-After", "10"))
                    time.sleep(retry)
                    attempt += 1
                    if attempt > max_retries:
                        resp.raise_for_status()
                    continue
                if resp.status_code >= 500:
                    if attempt >= max_retries:
                        resp.raise_for_status()
                    time.sleep(2 ** attempt)
                    attempt += 1
                    continue
                resp.raise_for_status()
                return resp
            except httpx.TransportError:
                if attempt >= max_retries:
                    raise
                time.sleep(2 ** attempt)
                attempt += 1

    def stream(self, path: str, **kwargs: Any):
        self._throttle()
        return self._client.stream("GET", path, **kwargs)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "PoliteClient":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
