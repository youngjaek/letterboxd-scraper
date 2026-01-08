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


def test_follow_graph_parses_display_names_and_avatars():
    html = read_fixture("following_page_rich.html")
    settings = make_settings()
    scraper = FollowGraphScraper(settings)
    mock_response = Mock(status_code=200, text=html)
    with patch.object(
        scraper.client, "get", side_effect=[mock_response, Mock(status_code=200, text="")]
    ):
        results = scraper.fetch_following("thebigal")
    assert results
    strange = next((r for r in results if r.username == "strangeharbors"), None)
    assert strange is not None
    assert strange.display_name == "Jeff Zhang"
    assert strange.avatar_url.endswith("-0-1000-0-1000-crop.jpg?v=123")
    assert strange.avatar_url.startswith("//a.ltrbxd.com")
    jesse = next((r for r in results if r.username == "jesseonplex"), None)
    assert jesse is not None
    assert jesse.display_name == "jesseonplex"
    assert jesse.avatar_url.endswith("-0-1000-0-1000-crop.jpg?v=456")


def test_follow_graph_fetches_profile_metadata():
    html = read_fixture("user_profile.html")
    settings = make_settings()
    scraper = FollowGraphScraper(settings)
    mock_response = Mock(status_code=200, text=html)
    with patch.object(scraper.client, "get", return_value=mock_response):
        result = scraper.fetch_profile_metadata("strangeharbors")
    assert result is not None
    assert result.display_name == "Jeff Zhang"
    assert result.avatar_url.endswith("-0-1000-0-1000-crop.jpg?v=6b85f4c57f")
