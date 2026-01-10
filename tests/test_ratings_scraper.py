from pathlib import Path
from unittest.mock import Mock, patch

from letterboxd_scraper.scrapers.ratings import ProfileRatingsScraper
from letterboxd_scraper.config import (
    Settings,
    DatabaseSettings,
    ScraperSettings,
    RSSSettings,
    CohortDefaults,
    TMDBSettings,
)


def read_fixture(name: str) -> str:
    path = Path(__file__).parent / "fixtures" / name
    return path.read_text(encoding="utf-8")


def make_settings() -> Settings:
    return Settings(
        database=DatabaseSettings(url="sqlite:///:memory:"),
        scraper=ScraperSettings(user_agent="test"),
        rss=RSSSettings(),
        tmdb=TMDBSettings(api_key="test-key"),
        cohort_defaults=CohortDefaults(),
        raw={},
    )


def test_profile_ratings_parses_films():
    html = read_fixture("ratings_page.html")
    profile_html = "<html></html>"
    settings = make_settings()
    scraper = ProfileRatingsScraper(settings)
    with patch.object(
        scraper.client,
        "get",
        side_effect=[
            Mock(status_code=200, text=profile_html),
            Mock(status_code=200, text=html),
            Mock(status_code=200, text=""),
        ],
    ):
        ratings = list(scraper.fetch_user_ratings("testuser"))
    assert len(ratings) == 1
    assert ratings[0].film_slug == "film-slug"
    assert ratings[0].rating == 3.5
    assert ratings[0].letterboxd_film_id == 101
    assert ratings[0].release_year == 2012


def test_profile_ratings_handles_data_attribute(monkeypatch):
    html = """
    <li class="poster-container" data-film-slug="film-two" data-rating="4.5">
        <div data-film-slug="film-two"></div>
        <img alt="Film Two" />
    </li>
    """
    profile_html = "<html></html>"
    settings = make_settings()
    scraper = ProfileRatingsScraper(settings)
    with patch.object(
        scraper.client,
        "get",
        side_effect=[
            Mock(status_code=200, text=profile_html),
            Mock(status_code=200, text=html),
            Mock(status_code=200, text=""),
        ],
    ):
        ratings = list(scraper.fetch_user_ratings("testuser"))
    assert len(ratings) == 1
    assert ratings[0].film_slug == "film-two"
    assert ratings[0].rating == 4.5
    assert ratings[0].letterboxd_film_id is None
    assert ratings[0].release_year is None


def test_profile_ratings_supports_grid_layout():
    html = read_fixture("ratings_grid_page.html")
    profile_html = "<html></html>"
    settings = make_settings()
    scraper = ProfileRatingsScraper(settings)
    with patch.object(
        scraper.client,
        "get",
        side_effect=[
            Mock(status_code=200, text=profile_html),
            Mock(status_code=200, text=html),
            Mock(status_code=200, text=""),
        ],
    ):
        ratings = list(scraper.fetch_user_ratings("testuser"))
    assert len(ratings) == 2
    assert ratings[0].film_slug == "film-alpha"
    assert ratings[0].rating == 4.5
    assert ratings[0].release_year == 1999
    assert ratings[1].film_slug == "film-beta"
    assert ratings[1].rating == 2.0
    assert ratings[1].release_year == 2005


def test_profile_ratings_captures_like_and_favorite_flags():
    html = """
    <ul>
        <li class="poster-container" data-film-slug="liked-film" data-film-id="201" data-film-release-year="2010">
            <img alt="Liked Film" />
            <span class="rating rated-8"></span>
            <p class="poster-viewingdata">
                <span class="like icon-liked"></span>
            </p>
        </li>
        <li class="poster-container" data-film-slug="favorite-film" data-film-id="202" data-film-release-year="2011">
            <img alt="Favorite Film" />
            <span class="rating rated-4"></span>
            <div class="poster">
                <span class="poster-ribbon icon-favorite"></span>
            </div>
        </li>
        <li class="poster-container" data-film-slug="both-film" data-film-id="203" data-film-release-year="2012">
            <img alt="Both Film" />
            <span class="rating rated-10"></span>
            <p class="poster-viewingdata">
                <span class="like icon-liked is-liked"></span>
            </p>
            <div class="poster">
                <span class="poster-ribbon poster-favorite"></span>
            </div>
        </li>
    </ul>
    """
    profile_html = read_fixture("profile_page_with_favorites.html")
    settings = make_settings()
    scraper = ProfileRatingsScraper(settings)
    with patch.object(
        scraper.client,
        "get",
        side_effect=[
            Mock(status_code=200, text=profile_html),
            Mock(status_code=200, text=html),
            Mock(status_code=200, text=""),
        ],
    ):
        ratings = list(scraper.fetch_user_ratings("testuser"))
    assert len(ratings) == 3
    assert ratings[0].liked is True
    assert ratings[0].favorite is False
    assert ratings[0].letterboxd_film_id == 201
    assert ratings[0].release_year == 2010
    assert ratings[1].liked is False
    assert ratings[1].favorite is True
    assert ratings[1].letterboxd_film_id == 202
    assert ratings[1].release_year == 2011
    assert ratings[2].liked is True
    assert ratings[2].favorite is True
    assert ratings[2].letterboxd_film_id == 203
    assert ratings[2].release_year == 2012


def test_fetch_profile_favorites_returns_entries():
    profile_html = read_fixture("profile_page_with_favorites.html")
    settings = make_settings()
    scraper = ProfileRatingsScraper(settings)
    with patch.object(
        scraper.client,
        "get",
        return_value=Mock(status_code=200, text=profile_html),
    ):
        favorites = scraper.fetch_profile_favorites("testuser")
    assert {entry.film_slug for entry in favorites} == {"favorite-film", "both-film"}
    assert all(entry.favorite for entry in favorites)


def test_profile_likes_without_ratings():
    likes_html = read_fixture("likes_page.html")
    profile_html = "<html></html>"
    settings = make_settings()
    scraper = ProfileRatingsScraper(settings)
    with patch.object(
        scraper.client,
        "get",
        side_effect=[
            Mock(status_code=200, text=profile_html),
            Mock(status_code=200, text=likes_html),
            Mock(status_code=200, text=""),
        ],
    ):
        likes = list(scraper.fetch_user_liked_films("testuser"))
    assert len(likes) == 2
    assert likes[0].film_slug == "liked-one"
    assert likes[0].rating is None
    assert likes[0].release_year == 2010
