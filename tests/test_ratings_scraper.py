from pathlib import Path
from unittest.mock import Mock, patch

from letterboxd_scraper.scrapers.ratings import ProfileRatingsScraper
from letterboxd_scraper.config import (
    Settings,
    DatabaseSettings,
    ScraperSettings,
    RSSSettings,
    CohortDefaults,
)


def read_fixture(name: str) -> str:
    path = Path(__file__).parent / "fixtures" / name
    return path.read_text(encoding="utf-8")


def make_settings() -> Settings:
    return Settings(
        database=DatabaseSettings(url="sqlite:///:memory:"),
        scraper=ScraperSettings(user_agent="test"),
        rss=RSSSettings(),
        cohort_defaults=CohortDefaults(),
        raw={},
    )


def test_profile_ratings_parses_films():
    html = read_fixture("ratings_page.html")
    settings = make_settings()
    scraper = ProfileRatingsScraper(settings)
    mock_response = Mock(status_code=200, text=html)
    with patch.object(scraper.client, "get", side_effect=[mock_response, Mock(status_code=200, text="")]):
        ratings = list(scraper.fetch_user_ratings("testuser"))
    assert len(ratings) == 1
    assert ratings[0].film_slug == "film-slug"
    assert ratings[0].rating == 3.5


def test_profile_ratings_handles_data_attribute(monkeypatch):
    html = """
    <li class="poster-container" data-film-slug="film-two" data-rating="4.5">
        <div data-film-slug="film-two"></div>
        <img alt="Film Two" />
    </li>
    """
    settings = make_settings()
    scraper = ProfileRatingsScraper(settings)
    mock_response = Mock(status_code=200, text=html)
    with patch.object(scraper.client, "get", side_effect=[mock_response, Mock(status_code=200, text="")]):
        ratings = list(scraper.fetch_user_ratings("testuser"))
    assert len(ratings) == 1
    assert ratings[0].film_slug == "film-two"
    assert ratings[0].rating == 4.5


def test_profile_ratings_supports_grid_layout():
    html = read_fixture("ratings_grid_page.html")
    settings = make_settings()
    scraper = ProfileRatingsScraper(settings)
    mock_response = Mock(status_code=200, text=html)
    with patch.object(scraper.client, "get", side_effect=[mock_response, Mock(status_code=200, text="")]):
        ratings = list(scraper.fetch_user_ratings("testuser"))
    assert len(ratings) == 2
    assert ratings[0].film_slug == "film-alpha"
    assert ratings[0].rating == 4.5
    assert ratings[1].film_slug == "film-beta"
    assert ratings[1].rating == 2.0
