from __future__ import annotations

from datetime import datetime, timezone
import time
from decimal import Decimal
from typing import Iterable, Optional, Set

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError, OperationalError
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
    film = _find_film(session, slug, normalized_letterboxd)
    if film:
        _apply_film_metadata(film, slug, title, normalized_tmdb, normalized_letterboxd, release_year)
        return film
    bind = session.get_bind()
    dialect = bind.dialect.name if bind is not None else None
    if dialect == "postgresql":
        _ensure_film_exists_postgres(
            session,
            slug,
            title,
            normalized_tmdb,
            normalized_letterboxd,
            release_year,
        )
        film = _find_film(session, slug, normalized_letterboxd)
        if not film:
            raise RuntimeError(f"Film {slug} missing after insert attempt.")
        _apply_film_metadata(
            film,
            slug,
            title,
            normalized_tmdb,
            normalized_letterboxd,
            release_year,
        )
        return film
    return _create_film_with_savepoint(
        session,
        slug,
        title,
        normalized_tmdb,
        normalized_letterboxd,
        release_year,
    )


def upsert_ratings(
    session: Session,
    username: str,
    ratings: Iterable[FilmRating],
    *,
    touch_last_full: bool = True,
    touch_last_incremental: bool = False,
    favorite_slugs: Optional[Set[str]] = None,
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
    now = datetime.now(timezone.utc)
    if touch_last_full:
        user.last_full_scrape_at = now
    if touch_last_incremental:
        user.last_incremental_scrape_at = now
    session.flush()
    if favorite_slugs is not None:
        _sync_user_favorites(session, user.id, favorite_slugs)
    return touched


def _apply_film_metadata(
    film: models.Film,
    slug: str,
    title: str,
    tmdb_id: Optional[int],
    letterboxd_id: Optional[int],
    release_year: Optional[int],
) -> None:
    if film.slug != slug:
        film.slug = slug
    if title and film.title != title:
        film.title = title
    if tmdb_id and not film.tmdb_id:
        film.tmdb_id = tmdb_id
    if letterboxd_id and not film.letterboxd_film_id:
        film.letterboxd_film_id = letterboxd_id
    if release_year and not film.release_year:
        film.release_year = release_year


def get_user_rating_snapshot(session: Session, username: str) -> dict[str, Optional[float]]:
    """Return the existing `(slug -> rating)` map for a user."""
    stmt = (
        select(models.Film.slug, models.Rating.rating)
        .join(models.Rating, models.Rating.film_id == models.Film.id)
        .join(models.User, models.User.id == models.Rating.user_id)
        .where(models.User.letterboxd_username == username)
    )
    snapshot: dict[str, Optional[float]] = {}
    for slug, rating in session.execute(stmt):
        snapshot[slug] = _normalize_rating_value(rating)
    return snapshot


def rating_matches_snapshot(
    snapshot: Optional[dict[str, Optional[float]]],
    payload: FilmRating,
) -> bool:
    if not snapshot:
        return False
    if payload.film_slug not in snapshot:
        return False
    stored = snapshot[payload.film_slug]
    if stored is None and payload.rating is None:
        return True
    if stored is None or payload.rating is None:
        return False
    return abs(stored - payload.rating) < 1e-6


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


def _normalize_rating_value(value: Optional[float | Decimal]) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    return float(value)


def _sync_user_favorites(
    session: Session,
    user_id: int,
    favorite_slugs: Set[str],
) -> None:
    stmt = (
        select(models.Rating)
        .join(models.Film, models.Film.id == models.Rating.film_id)
        .where(models.Rating.user_id == user_id, models.Rating.favorite.is_(True))
    )
    if favorite_slugs:
        stmt = stmt.where(~models.Film.slug.in_(favorite_slugs))
    for rating in session.scalars(stmt):
        rating.favorite = False


def _ensure_film_exists_postgres(
    session: Session,
    slug: str,
    title: str,
    tmdb_id: Optional[int],
    letterboxd_id: Optional[int],
    release_year: Optional[int],
) -> None:
    bind = session.get_bind()
    if bind is None:
        raise RuntimeError("No engine bound to session while inserting films.")
    values: dict[str, Optional[int | str]] = {
        "slug": slug,
        "title": title,
        "tmdb_id": tmdb_id,
        "letterboxd_film_id": letterboxd_id,
        "release_year": release_year,
    }
    insert_stmt = pg_insert(models.Film).values(values).on_conflict_do_nothing()
    _execute_with_deadlock_retry(bind, insert_stmt)


def _create_film_with_savepoint(
    session: Session,
    slug: str,
    title: str,
    tmdb_id: Optional[int],
    letterboxd_id: Optional[int],
    release_year: Optional[int],
) -> models.Film:
    film = models.Film(slug=slug, title=title)
    _apply_film_metadata(film, slug, title, tmdb_id, letterboxd_id, release_year)
    savepoint = session.begin_nested()
    try:
        session.add(film)
        session.flush()
    except IntegrityError:
        savepoint.rollback()
        existing = _find_film(session, slug, letterboxd_id)
        if not existing:
            raise
        _apply_film_metadata(existing, slug, title, tmdb_id, letterboxd_id, release_year)
        return existing
    else:
        savepoint.commit()
        return film


def _find_film(session: Session, slug: Optional[str], letterboxd_id: Optional[int]) -> Optional[models.Film]:
    if letterboxd_id is not None:
        stmt = select(models.Film).where(models.Film.letterboxd_film_id == letterboxd_id)
        film = session.scalars(stmt).one_or_none()
        if film:
            return film
    if slug:
        stmt = select(models.Film).where(models.Film.slug == slug)
        film = session.scalars(stmt).one_or_none()
        if film:
            return film
    return None


def _execute_with_deadlock_retry(
    bind,
    statement,
    params: Optional[dict] = None,
    *,
    max_attempts: int = 5,
    base_delay: float = 0.05,
):
    last_exc: Optional[Exception] = None
    for attempt in range(max_attempts):
        try:
            with bind.begin() as conn:
                return conn.execute(statement, params or {})
        except OperationalError as exc:
            if not _is_deadlock_error(exc) or attempt == max_attempts - 1:
                raise
            last_exc = exc
            time.sleep(base_delay * (attempt + 1))
    if last_exc:
        raise last_exc


def _is_deadlock_error(exc: OperationalError) -> bool:
    orig = getattr(exc, "orig", None)
    code = getattr(orig, "pgcode", None)
    if code == "40P01":
        return True
    message = str(exc).lower()
    return "deadlock detected" in message
