from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from letterboxd_scraper.db import models
from letterboxd_scraper.scrapers.film_pages import FilmPageDetails
from letterboxd_scraper.services import enrichment
from letterboxd_scraper.services.tmdb import TMDBMoviePayload, TMDBPersonCredit


class FakeTMDBClient:
    def __init__(self, payload: TMDBMoviePayload, credits: list[TMDBPersonCredit]):
        self.payload = payload
        self.credits = credits
        self.called_with = []

    def fetch_movie_with_credits(self, tmdb_id: int):
        self.called_with.append(tmdb_id)
        return self.payload, self.credits


class FakeFilmPageScraper:
    def __init__(self, details: FilmPageDetails):
        self.details = details
        self.calls = []

    def fetch(self, slug: str) -> FilmPageDetails:
        self.calls.append(slug)
        return self.details


def make_session() -> Session:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    models.Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    return SessionLocal()


def test_enrich_film_metadata_populates_fields_and_directors():
    session = make_session()
    film = models.Film(slug="sample-film", title="Old Title")
    session.add(film)
    session.commit()
    payload = TMDBMoviePayload(
        tmdb_id=10,
        imdb_id="tt001",
        title="New Title",
        original_title="Orig Title",
        runtime_minutes=115,
        release_date=date(2023, 5, 4),
        overview="Synopsis",
        poster_url="https://image/poster.jpg",
        genres=[{"id": 1}],
        origin_countries=[{"iso_3166_1": "US"}],
        raw={"poster_path": "/poster.jpg"},
    )
    credits = [
        TMDBPersonCredit(person_id=1, name="Director One", job="Director", department="Directing", credit_order=2),
        TMDBPersonCredit(person_id=2, name="Writer", job="Writer", department="Writing", credit_order=1),
        TMDBPersonCredit(person_id=3, name="Director Two", job="Director", department="Directing", credit_order=None),
    ]
    client = FakeTMDBClient(payload, credits)

    enriched = enrichment.enrich_film_metadata(session, film, client, tmdb_id=10)
    session.commit()

    assert enriched is True
    assert film.tmdb_id == 10
    assert film.release_year == 2023
    assert film.runtime_minutes == 115
    assert film.poster_url == "https://image/poster.jpg"
    assert film.genres == [{"id": 1}]
    directors = session.execute(
        select(models.FilmPerson).where(models.FilmPerson.film_id == film.id).order_by(models.FilmPerson.credit_order)
    ).scalars().all()
    assert [director.name for director in directors] == ["Director One", "Director Two"]
    session.close()


def test_enrich_fetches_tmdb_id_from_film_page_when_missing():
    session = make_session()
    film = models.Film(slug="missing", title="Missing ID")
    session.add(film)
    session.commit()
    payload = TMDBMoviePayload(
        tmdb_id=77,
        imdb_id=None,
        title="Title",
        original_title=None,
        runtime_minutes=None,
        release_date=None,
        overview=None,
        poster_url=None,
        genres=[],
        origin_countries=[],
        raw={"ok": True},
    )
    client = FakeTMDBClient(payload, [])
    scraper = FakeFilmPageScraper(
        FilmPageDetails(slug="missing", tmdb_id=77, imdb_id="tt777", letterboxd_film_id=111)
    )

    enriched = enrichment.enrich_film_metadata(session, film, client, film_page_scraper=scraper)
    session.commit()

    assert enriched is True
    assert scraper.calls == ["missing"]
    assert film.tmdb_id == 77
    assert film.imdb_id == "tt777"
    session.close()


def test_enrich_returns_false_without_tmdb_id():
    session = make_session()
    film = models.Film(slug="no-id", title="No ID")
    session.add(film)
    session.commit()
    scraper = FakeFilmPageScraper(
        FilmPageDetails(slug="no-id", tmdb_id=None, imdb_id=None, letterboxd_film_id=None)
    )
    client = FakeTMDBClient(
        TMDBMoviePayload(
            tmdb_id=1,
            imdb_id=None,
            title="A",
            original_title=None,
            runtime_minutes=None,
            release_date=None,
            overview=None,
            poster_url=None,
            genres=[],
            origin_countries=[],
            raw={},
        ),
        [],
    )

    enriched = enrichment.enrich_film_metadata(session, film, client, film_page_scraper=scraper)
    assert enriched is False
    session.close()


def test_enrich_handles_tmdb_not_found_with_fallback_directors():
    session = make_session()
    film = models.Film(slug="episode", title="Episode Title")
    session.add(film)
    session.commit()
    payload = TMDBMoviePayload(
        tmdb_id=495632,
        imdb_id=None,
        title="Episode Title",
        original_title=None,
        runtime_minutes=None,
        release_date=None,
        overview=None,
        poster_url=None,
        genres=[],
        origin_countries=[],
        raw={},  # simulate 404
    )
    client = FakeTMDBClient(payload, [])
    scraper = FakeFilmPageScraper(
        FilmPageDetails(
            slug="episode",
            tmdb_id=495632,
            imdb_id=None,
            letterboxd_film_id=500,
            release_year=2016,
            directors=["Episode Director"],
        )
    )
    enriched = enrichment.enrich_film_metadata(session, film, client, film_page_scraper=scraper)
    session.commit()

    assert enriched is False
    assert film.release_year == 2016
    directors = session.execute(
        select(models.FilmPerson).where(models.FilmPerson.film_id == film.id)
    ).scalars().all()
    assert [d.name for d in directors] == ["Episode Director"]
    assert film.tmdb_payload.get("tmdb_not_found") is True
    assert enrichment.film_needs_enrichment(film) is False
    session.close()


def test_film_needs_enrichment_checks_fields():
    film = models.Film(
        slug="complete",
        title="Complete",
        tmdb_id=1,
        runtime_minutes=100,
        poster_url="poster",
        overview="desc",
        genres=[{"id": 1}],
    )
    assert enrichment.film_needs_enrichment(film) is False
    film.poster_url = None
    assert enrichment.film_needs_enrichment(film) is True
