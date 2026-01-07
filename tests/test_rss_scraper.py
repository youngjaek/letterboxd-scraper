from pathlib import Path

from letterboxd_scraper.scrapers.rss import RSSScraper, RSSEntry
from letterboxd_scraper.config import (
    Settings,
    DatabaseSettings,
    ScraperSettings,
    RSSSettings,
    CohortDefaults,
    TMDBSettings,
)


def make_settings() -> Settings:
    return Settings(
        database=DatabaseSettings(url="sqlite:///:memory:"),
        scraper=ScraperSettings(user_agent="test"),
        rss=RSSSettings(max_entries=2),
        tmdb=TMDBSettings(api_key="test-key"),
        cohort_defaults=CohortDefaults(),
        raw={},
    )


def test_rss_scraper_filters_entries(monkeypatch):
    settings = make_settings()
    scraper = RSSScraper(settings)

    class MockFeed:
        entries = [
            {
                "letterboxd_film_slug": "slug1",
                "title": "Film 1",
                "letterboxd_member_rating": "3.5",
                "letterboxd_watched_date": "2025-12-24",
                "tmdb_movie_id": "123",
            },
            {
                "letterboxd_film_slug": "slug2",
                "title": "Film 2",
                "letterboxd_member_rating": "4.0",
                "tmdb_movieid": "456",
            },
        ]

    monkeypatch.setattr("letterboxd_scraper.scrapers.rss.feedparser.parse", lambda url: MockFeed())
    entries = list(scraper.fetch_feed("user"))
    assert len(entries) == 2
    assert isinstance(entries[0], RSSEntry)
    assert entries[0].watched_date.isoformat() == "2025-12-24"
    assert entries[0].tmdb_id == "123"
    assert entries[1].tmdb_id == "456"


def test_rss_scraper_parses_real_fixture(monkeypatch, tmp_path):
    settings = make_settings()
    settings.rss.max_entries = 5
    scraper = RSSScraper(settings)
    fixture_path = Path(__file__).parent / "fixtures" / "rss_sample.xml"

    class MockFeed:
        entries = []

    import feedparser

    real_feed = feedparser.parse(str(fixture_path))

    def mock_parse(url):
        return real_feed

    monkeypatch.setattr("letterboxd_scraper.scrapers.rss.feedparser.parse", mock_parse)
    entries = list(scraper.fetch_feed("sample_user"))
    assert len(entries) == settings.rss.max_entries
    assert entries[0].film_slug == "the-passion-according-to-gh"
    assert entries[0].rating == 2.0
    assert entries[0].film_title == "The Passion According to G.H."
    assert entries[0].tmdb_id == "566268"
