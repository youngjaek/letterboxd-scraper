from pathlib import Path
from unittest.mock import Mock, patch

from letterboxd_scraper.scrapers.follow_graph import FollowGraphScraper
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


def test_follow_graph_parses_usernames(tmp_path):
    html = read_fixture("following_page.html")
    settings = make_settings()
    scraper = FollowGraphScraper(settings)
    mock_response = Mock(status_code=200, text=html)
    with patch.object(
        scraper.client, "get", side_effect=[mock_response, Mock(status_code=200, text="")]
    ):
        results = scraper.fetch_following("testuser")
    assert len(results) == 2
    assert results[0].username == "alice"
    assert results[1].username == "bob"
