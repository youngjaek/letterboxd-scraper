from __future__ import annotations

from typing import Iterable, Optional, Sequence

from sqlalchemy.orm import Session

from ..db import models
from .tmdb import TMDBClient, TMDBPersonCredit
from ..scrapers.film_pages import FilmPageScraper


def enrich_film_metadata(
    session: Session,
    film: models.Film,
    client: TMDBClient,
    *,
    tmdb_id: Optional[int] = None,
    film_page_scraper: Optional[FilmPageScraper] = None,
) -> bool:
    """
    Hydrate a film row with TMDB metadata and overwrite existing director credits.

    Returns True when enrichment succeeds, False if the film has no TMDB ID.
    """
    target_tmdb_id = tmdb_id or film.tmdb_id
    if film_page_scraper:
        details = film_page_scraper.fetch(film.slug)
        _apply_film_page_details(session, film, details, sync_directors=False)
        if not target_tmdb_id:
            target_tmdb_id = details.tmdb_id
    tmdb_blocked = isinstance(film.tmdb_payload, dict) and film.tmdb_payload.get("tmdb_not_found")
    if tmdb_blocked:
        if film_page_scraper:
            details = film_page_scraper.fetch(film.slug)
            _apply_film_page_details(session, film, details, sync_directors=True)
        return False
    if not target_tmdb_id:
        return False

    movie_payload, credits = client.fetch_movie_with_credits(target_tmdb_id)
    if not movie_payload.raw:
        film.tmdb_payload = {"tmdb_not_found": True}
        if film_page_scraper:
            details = film_page_scraper.fetch(film.slug)
            _apply_film_page_details(session, film, details, sync_directors=True)
        return False
    film.tmdb_id = target_tmdb_id
    if movie_payload.imdb_id:
        film.imdb_id = movie_payload.imdb_id
    film.title = movie_payload.title or film.title
    film.release_date = movie_payload.release_date
    if movie_payload.release_date:
        film.release_year = movie_payload.release_date.year
    film.runtime_minutes = movie_payload.runtime_minutes
    film.poster_url = movie_payload.poster_url or film.poster_url
    film.overview = movie_payload.overview
    film.origin_countries = movie_payload.origin_countries
    film.genres = movie_payload.genres
    film.tmdb_payload = movie_payload.raw

    _sync_directors(session, film, credits)
    return True


def _sync_directors(session: Session, film: models.Film, credits: Iterable[TMDBPersonCredit]) -> None:
    directors = [credit for credit in credits if (credit.job or "").lower() == "director"]
    session.query(models.FilmPerson).filter(
        models.FilmPerson.film_id == film.id, models.FilmPerson.role == "director"
    ).delete(synchronize_session=False)
    for idx, director in enumerate(directors):
        credit_order = director.credit_order if director.credit_order is not None else 1000 + idx
        session.add(
            models.FilmPerson(
                film_id=film.id,
                person_id=director.person_id,
                name=director.name,
                role="director",
                credit_order=credit_order,
            )
        )


def _apply_film_page_details(
    session: Session,
    film: models.Film,
    details: FilmPageDetails,
    *,
    sync_directors: bool,
) -> None:
    if details.tmdb_id and not film.tmdb_id:
        film.tmdb_id = details.tmdb_id
    if details.imdb_id and not film.imdb_id:
        film.imdb_id = details.imdb_id
    if details.release_year and not film.release_year:
        film.release_year = details.release_year
    if sync_directors and details.directors:
        _sync_manual_directors(session, film, details.directors)


def _sync_manual_directors(session: Session, film: models.Film, names: Sequence[str]) -> None:
    if not names:
        return
    session.query(models.FilmPerson).filter(
        models.FilmPerson.film_id == film.id, models.FilmPerson.role == "director"
    ).delete(synchronize_session=False)
    for idx, name in enumerate(names):
        session.add(
            models.FilmPerson(
                film_id=film.id,
                person_id=None,
                name=name,
                role="director",
                credit_order=1000 + idx,
            )
        )


def film_needs_enrichment(film: models.Film) -> bool:
    tmdb_not_found = isinstance(film.tmdb_payload, dict) and film.tmdb_payload.get("tmdb_not_found")
    missing_director = not any(person.role == "director" for person in getattr(film, "people", []))
    if tmdb_not_found:
        return film.release_year is None or missing_director
    if not film.tmdb_id:
        return True
    if film.runtime_minutes is None:
        return True
    if not film.poster_url:
        return True
    if film.overview in (None, ""):
        return True
    if not film.genres:
        return True
    if film.release_year is None:
        return True
    if missing_director:
        return True
    return False
