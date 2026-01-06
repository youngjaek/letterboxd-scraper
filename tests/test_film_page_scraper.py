from types import SimpleNamespace

from letterboxd_scraper.scrapers.film_pages import FilmPageScraper
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
        scraper=ScraperSettings(user_agent="test-agent"),
        rss=RSSSettings(),
        tmdb=TMDBSettings(api_key="test"),
        cohort_defaults=CohortDefaults(),
        raw={},
    )


def test_film_page_scraper_parses_ids(monkeypatch):
    settings = make_settings()
    scraper = FilmPageScraper(settings)
    html = """
    <html>
        <body data-tmdb-id="1234" data-film-id="5678">
            <h1 class="headline-1">Film <small>2001</small></h1>
            <a href="https://www.imdb.com/title/tt0123456/">IMDB</a>
            <a href="/director/sample-director/">Sample Director</a>
        </body>
    </html>
    """
    monkeypatch.setattr(scraper.client, "get", lambda url: SimpleNamespace(text=html))

    details = scraper.fetch("sample-film")
    assert details.tmdb_id == 1234
    assert details.letterboxd_film_id == 5678
    assert details.release_year == 2001
    assert details.directors == ["Sample Director"]


def test_film_page_scraper_handles_releasedate_block(monkeypatch):
    settings = make_settings()
    scraper = FilmPageScraper(settings)
    html = """
    <html>
        <body data-film-id="999">
            <div class="productioninfo">
                <span class="releasedate"><a href="/films/year/2016/">2016</a></span>
            </div>
            <p class="credits">
                <span class="creatorlist">
                    <a class="contributor" href="/director/jane-doe/">Jane Doe</a>
                </span>
            </p>
        </body>
    </html>
    """
    monkeypatch.setattr(scraper.client, "get", lambda url: SimpleNamespace(text=html))
    details = scraper.fetch("episode-film")
    assert details.release_year == 2016
    assert details.directors == ["Jane Doe"]
