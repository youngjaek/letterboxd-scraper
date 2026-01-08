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
            <meta property="og:image" content="https://image.example/poster.jpg" />
            <meta property="og:description" content="Sample synopsis" />
            <h1 class="headline-1">Film <small>2001</small></h1>
            <a href="https://www.imdb.com/title/tt0123456/">IMDB</a>
            <a href="/director/sample-director/">Sample Director</a>
            <section>
                <a href="/films/genre/crime/">Crime</a>
            </section>
        </body>
    </html>
    """
    monkeypatch.setattr(scraper.client, "get", lambda url: SimpleNamespace(text=html))

    details = scraper.fetch("sample-film")
    assert details.tmdb_id == 1234
    assert details.tmdb_media_type == "movie"
    assert details.letterboxd_film_id == 5678
    assert details.release_year == 2001
    assert details.poster_url == "https://image.example/poster.jpg"
    assert details.overview == "Sample synopsis"
    assert details.genres == ["Crime"]
    assert [d.name for d in details.directors] == ["Sample Director"]


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
    assert [d.name for d in details.directors] == ["Jane Doe"]
    assert details.directors[0].slug == "jane-doe"


def test_film_page_scraper_extracts_tmdb_from_button(monkeypatch):
    settings = make_settings()
    scraper = FilmPageScraper(settings)
    html = """
    <html>
        <body data-film-id="888" data-tmdb-id="">
            <p class="text-link text-footer">
                702 mins &nbsp; More at
                <a href="https://www.themoviedb.org/tv/79788/" class="micro-button">TMDB</a>
            </p>
        </body>
    </html>
    """
    monkeypatch.setattr(scraper.client, "get", lambda url: SimpleNamespace(text=html))
    details = scraper.fetch("miniseries")
    assert details.tmdb_id == 79788
    assert details.tmdb_media_type == "tv"
    assert details.runtime_minutes == 702


def test_film_page_scraper_detects_media_type_when_data_id_present(monkeypatch):
    settings = make_settings()
    scraper = FilmPageScraper(settings)
    html = """
    <html>
        <body data-film-id="777" data-tmdb-id="110534">
            <p class="text-link text-footer">
                300 mins &nbsp; More at
                <a href="https://www.themoviedb.org/tv/110534/" class="micro-button">TMDB</a>
            </p>
        </body>
    </html>
    """
    monkeypatch.setattr(scraper.client, "get", lambda url: SimpleNamespace(text=html))
    details = scraper.fetch("another-miniseries")
    assert details.tmdb_id == 110534
    assert details.tmdb_media_type == "tv"
    assert details.runtime_minutes == 300


def test_film_page_scraper_extracts_poster_and_genres(monkeypatch):
    settings = make_settings()
    scraper = FilmPageScraper(settings)
    html = """
    <html>
        <head>
            <meta property="og:image" content="https://image.example/poster.jpg" />
        </head>
        <body>
            <section>
                <a href="/films/genre/crime/">Crime</a>
                <a href="/films/genre/drama/">Drama</a>
                <a href="/films/genre/crime/">Crime</a>
            </section>
        </body>
    </html>
    """
    monkeypatch.setattr(scraper.client, "get", lambda url: SimpleNamespace(text=html))
    details = scraper.fetch("poster-film")
    assert details.poster_url == "https://image.example/poster.jpg"
    assert details.genres == ["Crime", "Drama"]
