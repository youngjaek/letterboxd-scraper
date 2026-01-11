from __future__ import annotations

import time
from typing import Callable, Optional

import httpx

from .config import Settings


class ThrottledClient:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.client = httpx.Client(
            headers={"User-Agent": settings.scraper.user_agent},
            timeout=settings.scraper.request_timeout_seconds,
            follow_redirects=True,
        )
        self._last_request_time: float = 0.0

    def get(self, url: str, *, retry_on: Optional[set[int]] = None) -> httpx.Response:
        retry_on = retry_on or {429, 500, 502, 503, 504}
        attempt = 0
        while True:
            self._throttle()
            response = self.client.get(url)
            if response.status_code in retry_on and attempt < self.settings.scraper.retry_limit:
                attempt += 1
                sleep_time = self.settings.scraper.retry_backoff_seconds * attempt
                time.sleep(sleep_time)
                continue
            response.raise_for_status()
            return response

    def close(self) -> None:
        self.client.close()

    def _throttle(self) -> None:
        elapsed = time.time() - self._last_request_time
        delay = max(0.0, self.settings.scraper.throttle_seconds - elapsed)
        if delay > 0:
            time.sleep(delay)
        self._last_request_time = time.time()
