from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable, Optional, Set

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import models
from ..scrapers.ratings import FilmRating
from .cohorts import get_or_create_user


def get_or_create_film(
    session: Session,
    slug: str,
    title: str,
    tmdb_id: Optional[str | int] = None,
    release_year: Optional[int] = None,
    letterboxd_film_id: Optional[str | int] = None,
) -> models.Film:
    normalized_letterboxd = _normalize_letterboxd_id(letterboxd_film_id)
    normalized_tmdb = _normalize_tmdb_id(tmdb_id)
    film = None
    if normalized_letterboxd is not None:
        stmt = select(models.Film).where(models.Film.letterboxd_film_id == normalized_letterboxd)
        film = session.scalars(stmt).one_or_none()
    if film is None:
        stmt = select(models.Film).where(models.Film.slug == slug)
        film = session.scalars(stmt).one_or_none()
    if film:
        if film.slug != slug:
            film.slug = slug
        if title and film.title != title:
            film.title = title
        if normalized_tmdb and not film.tmdb_id:
            film.tmdb_id = normalized_tmdb
        if normalized_letterboxd and not film.letterboxd_film_id:
            film.letterboxd_film_id = normalized_letterboxd
        if release_year and not film.release_year:
            film.release_year = release_year
        return film
    film = models.Film(slug=slug, title=title)
    if normalized_tmdb:
        film.tmdb_id = normalized_tmdb
    if normalized_letterboxd:
        film.letterboxd_film_id = normalized_letterboxd
    if release_year:
        film.release_year = release_year
    session.add(film)
    session.flush()
    return film


def upsert_ratings(
    session: Session,
    username: str,
    ratings: Iterable[FilmRating],
) -> Set[int]:
    user = get_or_create_user(session, username)
    touched: Set[int] = set()
    for payload in ratings:
        film = get_or_create_film(
            session,
            payload.film_slug,
            payload.film_title,
            letterboxd_film_id=payload.letterboxd_film_id,
            release_year=payload.release_year,
        )
        touched.add(film.id)
        rating = session.get(models.Rating, {"user_id": user.id, "film_id": film.id})
        if rating:
            if payload.rating is not None:
                rating.rating = payload.rating
                rating.updated_at = datetime.now(timezone.utc)
            rating.liked = bool(payload.liked)
            rating.favorite = bool(payload.favorite)
        else:
            rating = models.Rating(
                user_id=user.id,
                film_id=film.id,
                rating=payload.rating,
                liked=bool(payload.liked),
                favorite=bool(payload.favorite),
            )
            session.add(rating)
    return touched


def _normalize_tmdb_id(value: Optional[str | int]) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    value = value.strip()
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _normalize_letterboxd_id(value: Optional[str | int]) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    value = value.strip()
    if not value:
        return None
    if ":" in value:
        value = value.split(":")[-1]
    try:
        return int(value)
    except ValueError:
        return None
