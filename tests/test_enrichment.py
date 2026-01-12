from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from letterboxd_scraper.db import models
from letterboxd_scraper.scrapers.film_pages import FilmPageDetails
from letterboxd_scraper.services import enrichment
from letterboxd_scraper.services.tmdb import TMDBMediaPayload, TMDBPersonCredit


class FakeTMDBClient:
    def __init__(
        self,
        payload: TMDBMediaPayload,
        credits: List[TMDBPersonCredit],
        *,
        find_result: Optional[Dict[str, Any]] = None,
        person_details: Optional[Dict[int, Dict[str, Any]]] = None,
    ):
        self.payload = payload
        self.credits = credits
        self.find_result = find_result
        self.raise_once = False
        self.calls: List[Tuple[int, str, Optional[int], Optional[int], Optional[int]]] = []
        self.person_details = person_details or {}
        self.image_base_url = "https://image.tmdb.org/t/p/original"

    def fetch_media_with_credits(
        self,
        tmdb_id: int,
        media_type: str = "movie",
        *,
        show_id: Optional[int] = None,
        season_number: Optional[int] = None,
        episode_number: Optional[int] = None,
    ):
        self.calls.append((tmdb_id, media_type, show_id, season_number, episode_number))
        if self.raise_once:
            self.raise_once = False
            raise RuntimeError("forced failure")
        return self.payload, self.credits

    def find_by_external_imdb(self, imdb_id: str) -> Optional[Dict[str, Any]]:
        return self.find_result

    def fetch_person(self, person_id: int) -> Optional[Dict[str, Any]]:
        return self.person_details.get(person_id)


class FakeFilmPageScraper:
    def __init__(self, details: FilmPageDetails):
        self.details = details

    def fetch(self, slug: str, *, letterboxd_id: Optional[int] = None) -> FilmPageDetails:
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


def make_payload(media_type: str = "movie") -> TMDBMediaPayload:
    return TMDBMediaPayload(
        tmdb_id=42,
        media_type=media_type,
        imdb_id="tt0042",
        title="Updated Title",
        original_title="Updated Title",
        runtime_minutes=120,
        release_date=date(2023, 1, 2),
        overview="Overview",
        poster_url="https://image/poster.jpg",
        genres=[{"id": 1, "name": "Drama"}],
        origin_countries=[{"iso_3166_1": "us", "name": "United States"}],
        raw={"id": 42},
    )


def test_enrich_film_metadata_populates_fields_and_directors():
    session = make_session()
    film = models.Film(slug="sample", title="Old")
    session.add(film)
    session.commit()
    payload = make_payload()
    credits = [
        TMDBPersonCredit(person_id=1, name="Dir One", job="Director", department="Directing", credit_order=1),
        TMDBPersonCredit(person_id=2, name="Writer", job="Writer", department="Writing", credit_order=2),
        TMDBPersonCredit(person_id=3, name="Dir Two", job="Director", department="Directing", credit_order=None),
    ]
    client = FakeTMDBClient(
        payload,
        credits,
        person_details={
            1: {"profile_path": "/dir-one.jpg", "known_for_department": "Directing"},
            3: {"profile_path": None, "known_for_department": "Directing"},
        },
    )

    enriched = enrichment.enrich_film_metadata(session, film, client, tmdb_id=42)
    session.commit()

    assert enriched is True
    assert film.tmdb_id == 42
    assert film.tmdb_media_type == "movie"
    assert film.release_year == 2023
    assert film.poster_url == "https://image/poster.jpg"
    directors = session.execute(
        select(models.FilmPerson).where(models.FilmPerson.film_id == film.id).order_by(models.FilmPerson.credit_order)
    ).scalars().all()
    assert [d.person.name for d in directors] == ["Dir One", "Dir Two"]
    assert directors[0].person.profile_url == "https://image.tmdb.org/t/p/original/dir-one.jpg"
    assert [g.name for g in film.genres] == ["Drama"]
    assert [c.code for c in film.countries] == ["US"]
    session.close()


def test_enrich_reads_tmdb_id_from_film_page_when_missing():
    session = make_session()
    film = models.Film(slug="missing", title="Missing")
    session.add(film)
    session.commit()
    payload = make_payload()
    client = FakeTMDBClient(payload, [])
    scraper = FakeFilmPageScraper(
        FilmPageDetails(
            slug="missing",
            title="Missing",
            tmdb_id=payload.tmdb_id,
            imdb_id="tt0042",
            letterboxd_film_id=101,
            release_year=2022,
        )
    )

    enriched = enrichment.enrich_film_metadata(session, film, client, film_page_scraper=scraper)
    session.commit()

    assert enriched is True
    assert film.tmdb_id == payload.tmdb_id
    assert film.imdb_id == "tt0042"
    session.close()


def test_enrich_falls_back_to_imdb_lookup_on_failure():
    session = make_session()
    film = models.Film(slug="fallback", title="Fallback", imdb_id="tt999")
    session.add(film)
    session.commit()
    first_payload = make_payload()
    episode_payload = TMDBMediaPayload(
        tmdb_id=555,
        media_type="tv_episode",
        imdb_id="tt999",
        title="Episode",
        original_title="Episode",
        runtime_minutes=60,
        release_date=date(2025, 5, 5),
        overview="Episode overview",
        poster_url=None,
        genres=[],
        origin_countries=[],
        raw={"id": 555},
        show_id=777,
        season_number=5,
        episode_number=8,
    )
    credits = [TMDBPersonCredit(person_id=10, name="Episode Director", job="Director", department="Directing", credit_order=1)]
    client = FakeTMDBClient(first_payload, credits, find_result={
        "media_type": "tv_episode",
        "id": 555,
        "show_id": 777,
        "season_number": 5,
        "episode_number": 8,
    })
    client.payload = episode_payload
    client.raise_once = True

    enriched = enrichment.enrich_film_metadata(session, film, client, tmdb_id=999)
    session.commit()

    assert enriched is True
    assert film.tmdb_media_type == "tv_episode"
    assert film.tmdb_show_id == 777
    assert film.tmdb_season_number == 5
    assert film.tmdb_episode_number == 8
    assert film.release_year == 2025
    assert len(client.calls) == 2  # initial attempt + fallback
    session.close()


def test_film_enrichment_reasons_include_director_metadata_gap():
    session = make_session()
    film = models.Film(
        slug="needs-director-sync",
        title="Needs Director",
        tmdb_id=1,
        tmdb_media_type="movie",
        poster_url="poster",
        overview="summary",
        release_year=2020,
    )
    person = models.Person(tmdb_id=10, name="Director One")
    session.add_all([film, person])
    session.commit()
    film_person = models.FilmPerson(film_id=film.id, person=person, role="director", credit_order=1)
    session.add(film_person)
    session.commit()
    session.refresh(film)

    reasons = enrichment.film_enrichment_reasons(film)
    assert "director metadata incomplete" in reasons

    person.profile_url = "https://image/dir.jpg"
    person.tmdb_synced_at = datetime.now(timezone.utc)
    session.commit()
    session.refresh(film)

    refreshed_reasons = enrichment.film_enrichment_reasons(film)
    assert "director metadata incomplete" not in refreshed_reasons
    session.close()
