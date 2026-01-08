from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Dict, List, Optional, Tuple
import time

import httpx

from ..config import Settings


@dataclass
class TMDBPersonCredit:
    person_id: Optional[int]
    name: str
    job: Optional[str]
    department: Optional[str]
    credit_order: Optional[int]


@dataclass
class TMDBMediaPayload:
    tmdb_id: int
    media_type: str
    imdb_id: Optional[str]
    title: str
    original_title: Optional[str]
    runtime_minutes: Optional[int]
    release_date: Optional[date]
    overview: Optional[str]
    poster_url: Optional[str]
    genres: List[Dict[str, Any]]
    origin_countries: List[Dict[str, Any]]
    raw: Dict[str, Any]


class TMDBClient:
    """Thin wrapper around TMDB movie + credits endpoints with lightweight caching."""

    def __init__(
        self,
        settings: Settings,
        *,
        http_client: Optional[httpx.Client] = None,
        cache_ttl_seconds: int = 3600,
    ) -> None:
        if not settings.tmdb.api_key:
            raise ValueError("TMDB API key is not configured.")
        self.api_key = settings.tmdb.api_key
        self.base_url = settings.tmdb.base_url.rstrip("/")
        self.image_base_url = settings.tmdb.image_base_url.rstrip("/")
        timeout = settings.tmdb.request_timeout_seconds
        self._client = http_client or httpx.Client(timeout=timeout)
        self._cache_ttl = cache_ttl_seconds
        self._cache: Dict[str, Tuple[float, Dict[str, Any]]] = {}

    def fetch_movie(self, tmdb_id: int) -> TMDBMediaPayload:
        return self._fetch_media_payload(tmdb_id, media_type="movie")

    def fetch_credits(self, tmdb_id: int, media_type: str = "movie") -> List[TMDBPersonCredit]:
        path = "/tv/{}/credits" if media_type == "tv" else "/movie/{}/credits"
        data = self._request_json(path.format(tmdb_id))
        credits: List[TMDBPersonCredit] = []
        for crew in data.get("crew", []):
            credits.append(
                TMDBPersonCredit(
                    person_id=crew.get("id"),
                    name=crew.get("name") or "",
                    job=crew.get("job"),
                    department=crew.get("department"),
                    credit_order=crew.get("order"),
                )
            )
        return credits

    def fetch_media_with_credits(
        self,
        tmdb_id: int,
        media_type: str = "movie",
    ) -> Tuple[TMDBMediaPayload, List[TMDBPersonCredit]]:
        payload = self._fetch_media_payload(tmdb_id, media_type=media_type)
        credits = self.fetch_credits(tmdb_id, media_type=media_type)
        return payload, credits

    def close(self) -> None:
        self._client.close()

    def _request_json(self, path: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        params = params or {}
        params["api_key"] = self.api_key
        cache_key = self._cache_key(path, params)
        cached = self._cache.get(cache_key)
        if cached and (time.time() - cached[0]) < self._cache_ttl:
            return cached[1]
        url = f"{self.base_url}{path}"
        response = self._client.get(url, params=params)
        if response.status_code == 404:
            self._cache[cache_key] = (time.time(), {})
            return {}
        response.raise_for_status()
        data = response.json()
        self._cache[cache_key] = (time.time(), data)
        return data

    def _fetch_media_payload(self, tmdb_id: int, media_type: str) -> TMDBMediaPayload:
        if media_type == "tv":
            data = self._request_json(f"/tv/{tmdb_id}")
        else:
            data = self._request_json(f"/movie/{tmdb_id}")
        return self._parse_media_payload(tmdb_id, data, media_type)

    def _parse_media_payload(
        self, tmdb_id: int, data: Dict[str, Any], media_type: str
    ) -> TMDBMediaPayload:
        release_date_value = (
            data.get("first_air_date") if media_type == "tv" else data.get("release_date")
        )
        release_date = None
        if release_date_value:
            try:
                release_date = date.fromisoformat(release_date_value)
            except ValueError:
                release_date = None
        poster_path = data.get("poster_path")
        poster_url = f"{self.image_base_url}{poster_path}" if poster_path else None
        if media_type == "tv":
            title = data.get("name") or data.get("original_name") or ""
            original_title = data.get("original_name")
            runtime_field = data.get("episode_run_time") or []
            runtime_minutes = runtime_field[0] if runtime_field else None
            origin_countries = data.get("production_countries") or [
                {"iso_3166_1": code} for code in data.get("origin_country", [])
            ]
            imdb_id = None
        else:
            title = data.get("title") or data.get("original_title") or ""
            original_title = data.get("original_title")
            runtime_minutes = data.get("runtime")
            origin_countries = data.get("production_countries") or []
            imdb_id = data.get("imdb_id")
        return TMDBMediaPayload(
            tmdb_id=tmdb_id,
            media_type=media_type,
            imdb_id=imdb_id,
            title=title,
            original_title=original_title,
            runtime_minutes=runtime_minutes,
            release_date=release_date,
            overview=data.get("overview"),
            poster_url=poster_url,
            genres=data.get("genres") or [],
            origin_countries=origin_countries,
            raw=dict(data),
        )

    @staticmethod
    def _cache_key(path: str, params: Dict[str, Any]) -> str:
        serialized = "&".join(
            f"{key}={value}" for key, value in sorted(params.items())
        )
        return f"{path}?{serialized}"
