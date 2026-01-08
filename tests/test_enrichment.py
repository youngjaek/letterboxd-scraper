from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from letterboxd_scraper.db import models
from letterboxd_scraper.scrapers.film_pages import FilmPageDetails, PersonCredit
from letterboxd_scraper.scrapers.person_pages import PersonPageScraper
from letterboxd_scraper.services import enrichment
from letterboxd_scraper.services.tmdb import TMDBMediaPayload, TMDBPersonCredit


class FakeTMDBClient:
    def __init__(self, payload: TMDBMediaPayload, credits: list[TMDBPersonCredit]):
        self.payload = payload
        self.credits = credits
        self.called_with = []

    def fetch_media_with_credits(self, tmdb_id: int, media_type: str = "movie"):
        self.called_with.append((tmdb_id, media_type))
        return self.payload, self.credits


class FakeFilmPageScraper:
    def __init__(self, details: FilmPageDetails):
        self.details = details
        self.calls = []

    def fetch(self, slug: str) -> FilmPageDetails:
        self.calls.append(slug)
        return self.details


class FakePersonPageScraper:
    def __init__(self, mapping: Optional[dict[str, Optional[int]]] = None):
        self.mapping = mapping or {}
        self.calls: list[str] = []

    def fetch_tmdb_id(self, slug: str) -> Optional[int]:
        self.calls.append(slug)
        return self.mapping.get(slug)


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
    payload = TMDBMediaPayload(
        tmdb_id=10,
        media_type="movie",
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
    payload = TMDBMediaPayload(
        tmdb_id=77,
        media_type="movie",
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


def test_enrich_calls_tv_endpoint_when_media_type_is_tv():
    session = make_session()
    film = models.Film(slug="miniseries", title="Miniseries")
    session.add(film)
    session.commit()
    payload = TMDBMediaPayload(
        tmdb_id=79788,
        media_type="tv",
        imdb_id=None,
        title="Watchmen",
        original_title="Watchmen",
        runtime_minutes=60,
        release_date=date(2019, 10, 20),
        overview="TV overview",
        poster_url="poster-url",
        genres=[{"id": 1}],
        origin_countries=[{"iso_3166_1": "US"}],
        raw={"name": "Watchmen"},
    )
    credits = [
        TMDBPersonCredit(person_id=None, name="Damon Lindelof", job="Director", department="Directing", credit_order=1)
    ]
    client = FakeTMDBClient(payload, credits)
    scraper = FakeFilmPageScraper(
        FilmPageDetails(
            slug="miniseries",
            tmdb_id=79788,
            imdb_id=None,
            letterboxd_film_id=222,
            release_year=2019,
            directors=[PersonCredit(name="Damon Lindelof", slug="damon-lindelof")],
            tmdb_media_type="tv",
        )
    )
    person_scraper = FakePersonPageScraper({"damon-lindelof": 999})
    enriched = enrichment.enrich_film_metadata(
        session,
        film,
        client,
        film_page_scraper=scraper,
        person_page_scraper=person_scraper,
    )
    session.commit()

    assert enriched is True
    assert client.called_with == [(79788, "tv")]
    assert film.runtime_minutes is None
    assert film.release_year == 2019
    directors = session.execute(
        select(models.FilmPerson).where(models.FilmPerson.film_id == film.id)
    ).scalars().all()
    assert directors[0].person_id == 999
    session.close()


def test_enrich_falls_back_to_page_directors_when_tmdb_missing():
    session = make_session()
    film = models.Film(slug="miniseries", title="Miniseries")
    session.add(film)
    session.commit()
    payload = TMDBMediaPayload(
        tmdb_id=555,
        media_type="tv",
        imdb_id=None,
        title="Title",
        original_title="Orig",
        runtime_minutes=None,
        release_date=None,
        overview=None,
        poster_url=None,
        genres=[],
        origin_countries=[],
        raw={"name": "Title"},
    )
    client = FakeTMDBClient(payload, [])  # no directors in credits
    page_details = FilmPageDetails(
        slug="miniseries",
        tmdb_id=555,
        imdb_id=None,
        letterboxd_film_id=100,
        release_year=2020,
        directors=[
            PersonCredit(name="Lisa Cholodenko", slug="lisa-cholodenko-1"),
            PersonCredit(name="Michael Dinner", slug="michael-dinner"),
        ],
        tmdb_media_type="tv",
    )
    scraper = FakeFilmPageScraper(page_details)
    person_scraper = FakePersonPageScraper(
        {"lisa-cholodenko-1": 75699, "michael-dinner": 12345}
    )
    enriched = enrichment.enrich_film_metadata(
        session,
        film,
        client,
        film_page_scraper=scraper,
        person_page_scraper=person_scraper,
    )
    session.commit()
    assert enriched is True
    directors = session.execute(
        select(models.FilmPerson).where(models.FilmPerson.film_id == film.id)
    ).scalars().all()
    assert [d.name for d in directors] == ["Lisa Cholodenko", "Michael Dinner"]
    assert [d.person_id for d in directors] == [75699, 12345]
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
        TMDBMediaPayload(
            tmdb_id=1,
            media_type="movie",
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
    payload = TMDBMediaPayload(
        tmdb_id=495632,
        media_type="movie",
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
            runtime_minutes=300,
            poster_url="https://example/poster.jpg",
            genres=["Crime", "Drama"],
            directors=[PersonCredit(name="Episode Director", slug="episode-director")],
        )
    )
    person_scraper = FakePersonPageScraper({"episode-director": 101})
    enriched = enrichment.enrich_film_metadata(
        session,
        film,
        client,
        film_page_scraper=scraper,
        person_page_scraper=person_scraper,
    )
    session.commit()

    assert enriched is False
    assert film.release_year == 2016
    assert film.runtime_minutes == 300
    assert film.poster_url == "https://example/poster.jpg"
    assert film.genres == [{"name": "Crime"}, {"name": "Drama"}]
    directors = session.execute(
        select(models.FilmPerson).where(models.FilmPerson.film_id == film.id)
    ).scalars().all()
    assert [d.name for d in directors] == ["Episode Director"]
    assert directors[0].person_id == 101
    assert film.tmdb_payload.get("tmdb_not_found") is True
    assert enrichment.film_needs_enrichment(film) is False
    session.close()


def test_film_needs_enrichment_checks_fields():
    film = models.Film(
        slug="complete",
        title="Complete",
        tmdb_id=1,
        release_year=2020,
        runtime_minutes=100,
        poster_url="poster",
        overview="desc",
        genres=[{"id": 1}],
    )
    film.people = [
        models.FilmPerson(
            film_id=0,
            person_id=123,
            name="Director Example",
            role="director",
            credit_order=1,
        )
    ]
    assert enrichment.film_needs_enrichment(film) is False
    film.poster_url = None
    assert enrichment.film_needs_enrichment(film) is True
