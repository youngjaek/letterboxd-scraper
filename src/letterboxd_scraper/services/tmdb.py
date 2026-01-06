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
class TMDBMoviePayload:
    tmdb_id: int
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

    def fetch_movie(self, tmdb_id: int) -> TMDBMoviePayload:
        data = self._request_json(f"/movie/{tmdb_id}")
        return self._parse_movie_payload(tmdb_id, data)

    def fetch_credits(self, tmdb_id: int) -> List[TMDBPersonCredit]:
        data = self._request_json(f"/movie/{tmdb_id}/credits")
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

    def fetch_movie_with_credits(
        self, tmdb_id: int
    ) -> Tuple[TMDBMoviePayload, List[TMDBPersonCredit]]:
        return self.fetch_movie(tmdb_id), self.fetch_credits(tmdb_id)

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

    def _parse_movie_payload(self, tmdb_id: int, data: Dict[str, Any]) -> TMDBMoviePayload:
        release_date = None
        if data.get("release_date"):
            try:
                release_date = date.fromisoformat(data["release_date"])
            except ValueError:
                release_date = None
        poster_path = data.get("poster_path")
        poster_url = f"{self.image_base_url}{poster_path}" if poster_path else None
        return TMDBMoviePayload(
            tmdb_id=tmdb_id,
            imdb_id=data.get("imdb_id"),
            title=data.get("title") or data.get("original_title") or "",
            original_title=data.get("original_title"),
            runtime_minutes=data.get("runtime"),
            release_date=release_date,
            overview=data.get("overview"),
            poster_url=poster_url,
            genres=data.get("genres") or [],
            origin_countries=data.get("production_countries") or [],
            raw=data,
        )

    @staticmethod
    def _cache_key(path: str, params: Dict[str, Any]) -> str:
        serialized = "&".join(
            f"{key}={value}" for key, value in sorted(params.items())
        )
        return f"{path}?{serialized}"
