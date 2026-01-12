from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, Iterable, Optional

from sqlalchemy.orm import Session

from ..db import models
from .tmdb import TMDBClient, TMDBMediaPayload, TMDBPersonCredit
from ..scrapers.film_pages import FilmPageScraper


@dataclass
class TMDBMediaCandidate:
    tmdb_id: Optional[int]
    media_type: Optional[str]
    show_id: Optional[int] = None
    season_number: Optional[int] = None
    episode_number: Optional[int] = None


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
    candidate = TMDBMediaCandidate(
        tmdb_id=tmdb_id or film.tmdb_id,
        media_type=film.tmdb_media_type,
        show_id=film.tmdb_show_id,
        season_number=film.tmdb_season_number,
        episode_number=film.tmdb_episode_number,
    )
    page_details = (
        film_page_scraper.fetch(film.slug, letterboxd_id=film.letterboxd_film_id)
        if film_page_scraper
        else None
    )
    if page_details:
        if not candidate.tmdb_id and page_details.tmdb_id:
            candidate.tmdb_id = page_details.tmdb_id
        if not candidate.media_type and page_details.tmdb_media_type:
            candidate.media_type = page_details.tmdb_media_type
        if page_details.letterboxd_film_id and film.letterboxd_film_id != page_details.letterboxd_film_id:
            film.letterboxd_film_id = page_details.letterboxd_film_id
        if page_details.slug and film.slug != page_details.slug:
            film.slug = page_details.slug
        if page_details.imdb_id and film.imdb_id != page_details.imdb_id:
            film.imdb_id = page_details.imdb_id
        if page_details.title and film.title != page_details.title:
            film.title = page_details.title
        if not film.release_year and page_details.release_year:
            film.release_year = page_details.release_year
    imdb_id = film.imdb_id
    payload, credits = _fetch_tmdb_payload(client, candidate, imdb_id)
    if payload is None and imdb_id:
        found = client.find_by_external_imdb(imdb_id)
        if found:
            candidate = _candidate_from_find_result(found)
            payload, credits = _fetch_tmdb_payload(client, candidate, imdb_id)
    if payload is None:
        film.tmdb_not_found = True
        return False
    if not _apply_tmdb_payload(session, film, payload):
        return False
    _sync_directors(session, film, credits, client)
    return True


def _candidate_from_find_result(found: Dict[str, Any]) -> TMDBMediaCandidate:
    media_type = found.get("media_type") or "movie"
    tmdb_id = found.get("id")
    show_id = found.get("show_id")
    season_number = found.get("season_number")
    episode_number = found.get("episode_number")
    if media_type == "tv" and not tmdb_id:
        tmdb_id = show_id
    if media_type != "tv_episode":
        show_id = None
        season_number = None
        episode_number = None
    return TMDBMediaCandidate(
        tmdb_id=tmdb_id,
        media_type=media_type,
        show_id=show_id,
        season_number=season_number,
        episode_number=episode_number,
    )


def _fetch_tmdb_payload(
    client: TMDBClient,
    candidate: TMDBMediaCandidate,
    imdb_id: Optional[str],
) -> tuple[Optional[TMDBMediaPayload], list[TMDBPersonCredit]]:
    if not candidate.tmdb_id and candidate.media_type != "tv_episode":
        return None, []
    media_type = candidate.media_type or "movie"
    try:
        payload, credits = client.fetch_media_with_credits(
            candidate.tmdb_id or 0,
            media_type=media_type,
            show_id=candidate.show_id,
            season_number=candidate.season_number,
            episode_number=candidate.episode_number,
        )
    except Exception:  # pragma: no cover - defensive
        return None, []
    if imdb_id:
        if not payload.imdb_id:
            return None, []
        if imdb_id.lower() != payload.imdb_id.lower():
            return None, []
    return payload, credits


def _apply_tmdb_payload(session: Session, film: models.Film, payload: TMDBMediaPayload) -> bool:
    if payload.tmdb_id:
        conflict = (
            session.query(models.Film.id)
            .filter(
                models.Film.tmdb_id == payload.tmdb_id,
                models.Film.tmdb_media_type == payload.media_type,
                models.Film.id != film.id,
            )
            .first()
        )
        if conflict:
            return False
    film.tmdb_id = payload.tmdb_id
    film.tmdb_media_type = payload.media_type
    if payload.show_id:
        film.tmdb_show_id = payload.show_id
    else:
        film.tmdb_show_id = None
    if payload.season_number is not None:
        film.tmdb_season_number = payload.season_number
    else:
        film.tmdb_season_number = None
    if payload.episode_number is not None:
        film.tmdb_episode_number = payload.episode_number
    else:
        film.tmdb_episode_number = None
    if payload.imdb_id:
        film.imdb_id = payload.imdb_id
    if payload.title:
        film.title = payload.title
    film.release_date = payload.release_date
    if payload.release_date:
        film.release_year = payload.release_date.year
    if payload.runtime_minutes is not None:
        if film.runtime_minutes is None or payload.runtime_minutes > film.runtime_minutes:
            film.runtime_minutes = payload.runtime_minutes
    if payload.poster_url:
        film.poster_url = payload.poster_url
    if payload.overview:
        film.overview = payload.overview
    film.tmdb_not_found = False
    film.tmdb_synced_at = datetime.now(timezone.utc)
    _sync_genres(session, film, payload.genres or [])
    _sync_countries(session, film, payload.origin_countries or [])
    return True


def _sync_directors(
    session: Session,
    film: models.Film,
    credits: Iterable[TMDBPersonCredit],
    client: TMDBClient,
) -> bool:
    directors = [credit for credit in credits if (credit.job or "").lower() == "director"]
    session.query(models.FilmPerson).filter(
        models.FilmPerson.film_id == film.id, models.FilmPerson.role == "director"
    ).delete(synchronize_session=False)
    for idx, director in enumerate(directors):
        credit_order = director.credit_order if director.credit_order is not None else 1000 + idx
        person = _ensure_person(session, director, client)
        session.add(
            models.FilmPerson(
                film_id=film.id,
                person=person,
                role="director",
                credit_order=credit_order,
            )
        )
    return bool(directors)


def _sync_genres(
    session: Session,
    film: models.Film,
    genres: Iterable[Dict[str, object]],
) -> None:
    seen_ids: set[int] = set()
    resolved: list[models.Genre] = []
    for genre in genres:
        tmdb_id = genre.get("id")
        if not isinstance(tmdb_id, int):
            continue
        if tmdb_id in seen_ids:
            continue
        seen_ids.add(tmdb_id)
        name = (genre.get("name") or "").strip() if isinstance(genre.get("name"), str) else ""
        existing = (
            session.query(models.Genre).filter(models.Genre.tmdb_id == tmdb_id).one_or_none()
        )
        if not existing:
            existing = models.Genre(tmdb_id=tmdb_id, name=name)
            session.add(existing)
        elif name and existing.name != name:
            existing.name = name
        resolved.append(existing)
    film.genres = resolved


def _sync_countries(
    session: Session,
    film: models.Film,
    countries: Iterable[Dict[str, object]],
) -> None:
    seen_codes: set[str] = set()
    resolved: list[models.Country] = []
    for country in countries:
        raw_code = country.get("iso_3166_1")
        if not isinstance(raw_code, str):
            continue
        code = raw_code.strip().upper()
        if not code or code in seen_codes:
            continue
        seen_codes.add(code)
        name = country.get("name")
        country_obj = session.get(models.Country, code)
        if not country_obj:
            country_obj = models.Country(code=code, name=name if isinstance(name, str) else None)
            session.add(country_obj)
        elif isinstance(name, str) and name and country_obj.name != name:
            country_obj.name = name
        resolved.append(country_obj)
    film.countries = resolved


def _ensure_person(
    session: Session,
    credit: TMDBPersonCredit,
    client: TMDBClient,
) -> models.Person:
    person: Optional[models.Person] = None
    if credit.person_id:
        person = (
            session.query(models.Person)
            .filter(models.Person.tmdb_id == credit.person_id)
            .one_or_none()
        )
    if not person:
        person = models.Person(tmdb_id=credit.person_id, name=credit.name or "Unknown")
        session.add(person)
    elif credit.name and person.name != credit.name:
        person.name = credit.name
    needs_refresh = (
        credit.person_id is not None
        and (person.profile_url is None or person.known_for_department is None or person.tmdb_synced_at is None)
    )
    if needs_refresh:
        details = _fetch_person_details(client, credit.person_id)
        if details is not None:
            profile_path = details.get("profile_path")
            person.profile_url = (
                f"{client.image_base_url}{profile_path}"
                if isinstance(profile_path, str) and profile_path
                else None
            )
            department = details.get("known_for_department")
            if isinstance(department, str):
                person.known_for_department = department
            person.tmdb_synced_at = datetime.now(timezone.utc)
    return person


def _fetch_person_details(client: TMDBClient, person_id: int) -> Optional[Dict[str, object]]:
    try:
        data = client.fetch_person(person_id)
    except Exception:  # pragma: no cover - defensive
        return None
    return data or None


def film_needs_enrichment(film: models.Film) -> bool:
    tmdb_not_found = film.tmdb_not_found
    missing_director = not any(
        credit.role == "director"
        and getattr(credit, "person", None) is not None
        and getattr(credit.person, "tmdb_id", None) is not None
        for credit in getattr(film, "people", [])
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
