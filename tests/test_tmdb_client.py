from datetime import date
from typing import Any, Dict, Optional

import pytest

from letterboxd_scraper.config import (
    CohortDefaults,
    DatabaseSettings,
    RSSSettings,
    ScraperSettings,
    Settings,
    TMDBSettings,
)
from letterboxd_scraper.services.tmdb import TMDBClient, TMDBPersonCredit


class DummyResponse:
    def __init__(self, payload: Dict[str, Any], status_code: int = 200):
        self._payload = payload
        self.status_code = status_code

    def json(self) -> Dict[str, Any]:
        return self._payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class DummyHTTPClient:
    def __init__(self, responses: Optional[list[Any]] = None):
        self.responses = responses or []
        self.calls: list[tuple[str, Dict[str, Any]]] = []

    def get(self, url: str, params: Optional[Dict[str, Any]] = None) -> DummyResponse:
        self.calls.append((url, params or {}))
        entry: Any = self.responses.pop(0) if self.responses else {}
        status = 200
        payload = entry
        if isinstance(entry, tuple):
            payload, status = entry
        elif isinstance(entry, dict) and "_status" in entry:
            status = entry["_status"]
            payload = {k: v for k, v in entry.items() if k != "_status"}
        return DummyResponse(payload, status_code=status)


def make_settings(api_key: str = "key") -> Settings:
    return Settings(
        database=DatabaseSettings(url="sqlite:///:memory:"),
        scraper=ScraperSettings(user_agent="test-agent"),
        rss=RSSSettings(),
        tmdb=TMDBSettings(api_key=api_key, base_url="https://tmdb", image_base_url="https://image"),
        cohort_defaults=CohortDefaults(),
        raw={},
    )


def test_fetch_movie_uses_cache_and_parses_payload():
    responses = [
        {
            "title": "Example",
            "original_title": "Original Title",
            "release_date": "2024-01-02",
            "runtime": 123,
            "overview": "desc",
            "poster_path": "/poster.jpg",
            "imdb_id": "tt123",
            "genres": [{"id": 1}],
            "production_countries": [{"iso_3166_1": "US"}],
        }
    ]
    http_client = DummyHTTPClient(responses=responses)
    client = TMDBClient(make_settings(), http_client=http_client, cache_ttl_seconds=9999)

    payload1 = client.fetch_movie(42)
    payload2 = client.fetch_movie(42)

    assert payload1.title == "Example"
    assert payload1.release_date == date(2024, 1, 2)
    assert payload1.poster_url == "https://image/poster.jpg"
    assert payload2 is not payload1  # new dataclass instance
    assert len(http_client.calls) == 1  # cache hit prevented second request


def test_fetch_movie_handles_invalid_release_date():
    http_client = DummyHTTPClient(
        responses=[{"title": "No Date", "release_date": "invalid", "runtime": None}]
    )
    client = TMDBClient(make_settings(), http_client=http_client, cache_ttl_seconds=0)
    payload = client.fetch_movie(7)
    assert payload.release_date is None
    assert payload.poster_url is None


def test_fetch_credits_maps_directors():
    http_client = DummyHTTPClient(responses=[{"crew": [{"id": 5, "name": "A", "job": "Director"}]}])
    client = TMDBClient(make_settings(), http_client=http_client, cache_ttl_seconds=0)
    credits = client.fetch_credits(9)
    assert credits == [
        TMDBPersonCredit(person_id=5, name="A", job="Director", department=None, credit_order=None)
    ]


def test_request_json_includes_api_key():
    http_client = DummyHTTPClient(responses=[{"title": "X"}])
    client = TMDBClient(make_settings(api_key="abc123"), http_client=http_client, cache_ttl_seconds=0)
    client.fetch_movie(1)
    assert http_client.calls[0][1]["api_key"] == "abc123"


def test_fetch_movie_handles_404_gracefully():
    http_client = DummyHTTPClient(responses=[({}, 404)])
    client = TMDBClient(make_settings(), http_client=http_client, cache_ttl_seconds=0)
    payload = client.fetch_movie(999)
    assert payload.raw == {}
    assert payload.title == ""


def test_missing_api_key_raises():
    settings = make_settings(api_key=None)
    with pytest.raises(ValueError):
        TMDBClient(settings)


def test_fetch_tv_payload_includes_external_ids():
    http_client = DummyHTTPClient(
        responses=[
            {
                "name": "Sample Show",
                "first_air_date": "2020-01-01",
                "episode_run_time": [55],
                "origin_country": ["US"],
                "external_ids": {"imdb_id": "tt999"},
            }
        ]
    )
    client = TMDBClient(make_settings(), http_client=http_client, cache_ttl_seconds=0)
    payload = client._fetch_media_payload(5, "tv")
    assert payload.media_type == "tv"
    assert payload.imdb_id == "tt999"
    assert payload.runtime_minutes == 55


def test_find_by_external_imdb_returns_episode():
    http_client = DummyHTTPClient(
        responses=[
            {
                "movie_results": [],
                "tv_results": [],
                "tv_episode_results": [
                    {"id": 123, "media_type": "tv_episode", "show_id": 50, "season_number": 2, "episode_number": 7}
                ],
            }
        ]
    )
    client = TMDBClient(make_settings(), http_client=http_client, cache_ttl_seconds=0)
    result = client.find_by_external_imdb("tt123")
    assert result["media_type"] == "tv_episode"
    assert result["show_id"] == 50
