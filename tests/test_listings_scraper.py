from pathlib import Path
from unittest.mock import Mock, patch

from letterboxd_scraper.config import (
    CohortDefaults,
    DatabaseSettings,
    RSSSettings,
    ScraperSettings,
    Settings,
)
from letterboxd_scraper.scrapers.listings import PosterListingScraper


def read_fixture(name: str) -> str:
    path = Path(__file__).parent / "fixtures" / name
    return path.read_text(encoding="utf-8")


def make_settings() -> Settings:
    return Settings(
        database=DatabaseSettings(url="sqlite:///:memory:"),
        scraper=ScraperSettings(user_agent="test-agent"),
        rss=RSSSettings(),
        cohort_defaults=CohortDefaults(),
        raw={},
    )


def test_parse_filmography_fixture_extracts_slugs():
    html = read_fixture("filmography.htm")
    entries = PosterListingScraper.parse_html(html)
    assert entries
    assert entries[0].slug == "inglourious-basterds"
    assert any(entry.slug == "prometheus" for entry in entries)


def test_parse_letterboxd_list_fixture_with_highlight_markup():
    html = read_fixture("letterboxd_list.html")
    entries = PosterListingScraper.parse_html(html)
    assert len(entries) == 100
    assert entries[0].slug == "harakiri"
    assert any(entry.slug == "seven-samurai" for entry in entries)


def test_iter_list_entries_handles_multiple_pages():
    html_page_one = """
    <div class="poster-grid">
        <ul class="grid">
            <li data-film-slug="film-one" data-film-name="Film One"></li>
        </ul>
    </div>
    """
    html_page_two = """
    <div class="poster-grid">
        <ul class="grid">
            <li data-film-slug="film-two" data-film-name="Film Two"></li>
        </ul>
    </div>
    """
    settings = make_settings()
    scraper = PosterListingScraper(settings)
    responses = [
        Mock(status_code=200, text=html_page_one),
        Mock(status_code=200, text=html_page_two),
        Mock(status_code=200, text="<div></div>"),
    ]
    with patch.object(scraper.client, "get", side_effect=responses):
        slugs = [entry.slug for entry in scraper.iter_list_entries("user/list/sample")]
    scraper.close()
    assert slugs == ["film-one", "film-two"]
