from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, Optional

from sqlalchemy.orm import Session

from ..db import models
from .tmdb import TMDBClient, TMDBPersonCredit, TMDBMediaPayload
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
    page_details = film_page_scraper.fetch(film.slug) if film_page_scraper else None
    if page_details:
        if not candidate.tmdb_id and page_details.tmdb_id:
            candidate.tmdb_id = page_details.tmdb_id
        if not candidate.media_type and page_details.tmdb_media_type:
            candidate.media_type = page_details.tmdb_media_type
        if not film.imdb_id and page_details.imdb_id:
            film.imdb_id = page_details.imdb_id
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
        film.tmdb_payload = {"tmdb_not_found": True}
        return False
    _apply_tmdb_payload(film, payload)
    _sync_directors(session, film, credits)
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


def _apply_tmdb_payload(film: models.Film, payload: TMDBMediaPayload) -> None:
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
    if payload.origin_countries:
        film.origin_countries = payload.origin_countries
    if payload.genres:
        film.genres = payload.genres
    film.tmdb_payload = dict(payload.raw or {})
    film.tmdb_payload["media_type"] = payload.media_type


def _sync_directors(
    session: Session,
    film: models.Film,
    credits: Iterable[TMDBPersonCredit],
) -> bool:
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
    return bool(directors)


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
