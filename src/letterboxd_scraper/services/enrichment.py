from __future__ import annotations

from typing import Iterable, Optional, Sequence

from sqlalchemy.orm import Session

from ..db import models
from .tmdb import TMDBClient, TMDBPersonCredit
from ..scrapers.film_pages import FilmPageScraper, FilmPageDetails, PersonCredit
from ..scrapers.person_pages import PersonPageScraper


def enrich_film_metadata(
    session: Session,
    film: models.Film,
    client: TMDBClient,
    *,
    tmdb_id: Optional[int] = None,
    film_page_scraper: Optional[FilmPageScraper] = None,
    person_page_scraper: Optional[PersonPageScraper] = None,
) -> bool:
    """
    Hydrate a film row with TMDB metadata and overwrite existing director credits.

    Returns True when enrichment succeeds, False if the film has no TMDB ID.
    """
    def _ensure_page_details() -> Optional[FilmPageDetails]:
        nonlocal page_details
        if page_details is None and film_page_scraper:
            page_details = film_page_scraper.fetch(film.slug)
        return page_details

    target_tmdb_id = tmdb_id or film.tmdb_id
    media_type = "movie"
    page_details: Optional[FilmPageDetails] = None
    if film_page_scraper:
        page_details = _ensure_page_details()
        _apply_film_page_details(
            session,
            film,
            page_details,
            sync_directors=False,
            overwrite=False,
            person_page_scraper=person_page_scraper,
        )
        if page_details and page_details.tmdb_media_type:
            media_type = page_details.tmdb_media_type
        if not target_tmdb_id:
            target_tmdb_id = page_details.tmdb_id if page_details else None
    elif isinstance(film.tmdb_payload, dict):
        media_type = film.tmdb_payload.get("media_type", "movie")
    tmdb_blocked = isinstance(film.tmdb_payload, dict) and film.tmdb_payload.get("tmdb_not_found")
    if tmdb_blocked:
        fallback_details = _ensure_page_details()
        if fallback_details:
            _apply_film_page_details(
                session,
                film,
                fallback_details,
                sync_directors=True,
                overwrite=True,
                person_page_scraper=person_page_scraper,
            )
        return False
    if not target_tmdb_id:
        return False

    movie_payload, credits = client.fetch_media_with_credits(target_tmdb_id, media_type=media_type)
    if not movie_payload.raw:
        film.tmdb_payload = {"tmdb_not_found": True, "media_type": media_type}
        fallback_details = _ensure_page_details()
        if fallback_details:
            _apply_film_page_details(
                session,
                film,
                fallback_details,
                sync_directors=True,
                overwrite=True,
                person_page_scraper=person_page_scraper,
            )
        return False
    film.tmdb_id = target_tmdb_id
    if movie_payload.imdb_id:
        film.imdb_id = movie_payload.imdb_id
    film.title = movie_payload.title or film.title
    film.release_date = movie_payload.release_date
    if movie_payload.release_date:
        film.release_year = movie_payload.release_date.year
    if movie_payload.media_type != "tv" and movie_payload.runtime_minutes is not None:
        if film.runtime_minutes is None or movie_payload.runtime_minutes > film.runtime_minutes:
            film.runtime_minutes = movie_payload.runtime_minutes
    film.poster_url = movie_payload.poster_url or film.poster_url
    film.overview = movie_payload.overview
    film.origin_countries = movie_payload.origin_countries
    film.genres = movie_payload.genres
    payload_raw = dict(movie_payload.raw or {})
    payload_raw["media_type"] = movie_payload.media_type
    film.tmdb_payload = payload_raw

    fallback_map = (
        {credit.name.strip().lower(): credit for credit in page_details.directors}
        if page_details and page_details.directors
        else None
    )
    added_tmdb_directors = _sync_directors(
        session,
        film,
        credits,
        fallback_directors=fallback_map,
        person_page_scraper=person_page_scraper,
    )
    if not added_tmdb_directors and page_details and page_details.directors:
        _sync_manual_directors(
            session,
            film,
            page_details.directors,
            person_page_scraper=person_page_scraper,
        )
    return True


def _sync_directors(
    session: Session,
    film: models.Film,
    credits: Iterable[TMDBPersonCredit],
    *,
    fallback_directors: Optional[dict[str, PersonCredit]] = None,
    person_page_scraper: Optional[PersonPageScraper] = None,
) -> bool:
    directors = [credit for credit in credits if (credit.job or "").lower() == "director"]
    session.query(models.FilmPerson).filter(
        models.FilmPerson.film_id == film.id, models.FilmPerson.role == "director"
    ).delete(synchronize_session=False)
    for idx, director in enumerate(directors):
        credit_order = director.credit_order if director.credit_order is not None else 1000 + idx
        tmdb_person_id = director.person_id
        if tmdb_person_id is None and fallback_directors:
            fallback = fallback_directors.get(director.name.strip().lower())
            if fallback and fallback.slug and person_page_scraper:
                tmdb_person_id = person_page_scraper.fetch_tmdb_id(fallback.slug)
        session.add(
            models.FilmPerson(
                film_id=film.id,
                person_id=tmdb_person_id,
                name=director.name,
                role="director",
                credit_order=credit_order,
            )
        )
    return bool(directors)


def _apply_film_page_details(
    session: Session,
    film: models.Film,
    details: FilmPageDetails,
    *,
    sync_directors: bool,
    overwrite: bool = False,
    person_page_scraper: Optional[PersonPageScraper] = None,
) -> None:
    def _maybe_assign(attr: str, value: Optional[int | str | list]) -> None:
        if value is None:
            return
        current = getattr(film, attr)
        if overwrite or current in (None, [], ""):
            setattr(film, attr, value)

    if details.tmdb_id and (overwrite or not film.tmdb_id):
        film.tmdb_id = details.tmdb_id
    if details.imdb_id:
        _maybe_assign("imdb_id", details.imdb_id)
    if details.release_year:
        _maybe_assign("release_year", details.release_year)
    if details.runtime_minutes:
        _maybe_assign("runtime_minutes", details.runtime_minutes)
    if details.poster_url:
        _maybe_assign("poster_url", details.poster_url)
    if details.overview:
        _maybe_assign("overview", details.overview)
    if details.genres:
        fallback_genres = [{"name": name} for name in details.genres]
        _maybe_assign("genres", fallback_genres)
    if sync_directors and details.directors:
        _sync_manual_directors(session, film, details.directors, person_page_scraper=person_page_scraper)


def _sync_manual_directors(
    session: Session,
    film: models.Film,
    directors: Sequence[PersonCredit],
    *,
    person_page_scraper: Optional[PersonPageScraper] = None,
) -> None:
    if not directors:
        return
    session.query(models.FilmPerson).filter(
        models.FilmPerson.film_id == film.id, models.FilmPerson.role == "director"
    ).delete(synchronize_session=False)
    for idx, director in enumerate(directors):
        tmdb_person_id = None
        if director.slug and person_page_scraper:
            tmdb_person_id = person_page_scraper.fetch_tmdb_id(director.slug)
        session.add(
            models.FilmPerson(
                film_id=film.id,
                person_id=tmdb_person_id,
                name=director.name,
                role="director",
                credit_order=1000 + idx,
            )
        )


def film_needs_enrichment(film: models.Film) -> bool:
    tmdb_not_found = isinstance(film.tmdb_payload, dict) and film.tmdb_payload.get("tmdb_not_found")
    missing_director = not any(
        person.role == "director" and person.person_id is not None
        for person in getattr(film, "people", [])
    )
    if tmdb_not_found:
        return film.release_year is None or missing_director
    if not film.tmdb_id:
        return True
    if not film.poster_url:
        return True
    if film.overview in (None, ""):
        return True
    if film.release_year is None:
        return True
    if missing_director:
        return True
    return False
