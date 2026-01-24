from __future__ import annotations

import time
from http.cookies import SimpleCookie
from typing import Callable, Optional

import httpx

from .config import Settings


class ThrottledClient:
    def __init__(self, settings: Settings):
        self.settings = settings
        headers = {
            "User-Agent": settings.scraper.user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
        }
        cookies = None
        if settings.scraper.session_cookie:
            cookies = httpx.Cookies()
            parsed = SimpleCookie()
            parsed.load(settings.scraper.session_cookie)
            if parsed:
                for key, morsel in parsed.items():
                    cookies.set(key, morsel.value)
            else:
                raw = settings.scraper.session_cookie.strip()
                if raw:
                    name = "letterboxd_session"
                    value = raw
                    if "=" in raw:
                        name, value = raw.split("=", 1)
                    cookies.set(name.strip(), value.strip())
        self.client = httpx.Client(
            headers=headers,
            timeout=settings.scraper.request_timeout_seconds,
            follow_redirects=True,
            cookies=cookies,
        )
        self._last_request_time: float = 0.0

    def get(self, url: str, *, retry_on: Optional[set[int]] = None) -> httpx.Response:
        retry_on = retry_on or {429, 500, 502, 503, 504}
        attempt = 0
        while True:
            self._throttle()
            try:
                response = self.client.get(url)
            except httpx.TimeoutException as exc:
                if attempt >= self.settings.scraper.retry_limit:
                    raise
                attempt += 1
                sleep_time = self.settings.scraper.retry_backoff_seconds * attempt
                time.sleep(sleep_time)
                continue
            if response.status_code == 403:
                message = (
                    "Received HTTP 403 from Letterboxd while requesting "
                    f"{url}. Many users resolve this by setting SCRAPER_USER_AGENT "
                    "to a real browser UA so the site does not reject the scraper. "
                    f"Current agent: {self.settings.scraper.user_agent!r}"
                )
                raise httpx.HTTPStatusError(
                    message,
                    request=response.request,
                    response=response,
                )
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
