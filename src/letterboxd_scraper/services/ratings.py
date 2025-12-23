from __future__ import annotations

from datetime import datetime
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import models
from ..scrapers.ratings import FilmRating
from .cohorts import get_or_create_user


def get_or_create_film(session: Session, slug: str, title: str) -> models.Film:
    stmt = select(models.Film).where(models.Film.slug == slug)
    film = session.scalars(stmt).one_or_none()
    if film:
        if title and film.title != title:
            film.title = title
        return film
    film = models.Film(slug=slug, title=title)
    session.add(film)
    session.flush()
    return film


def upsert_ratings(
    session: Session,
    username: str,
    ratings: Iterable[FilmRating],
) -> None:
    user = get_or_create_user(session, username)
    for payload in ratings:
        film = get_or_create_film(session, payload.film_slug, payload.film_title)
        rating = session.get(models.Rating, {"user_id": user.id, "film_id": film.id})
        if rating:
            rating.rating = payload.rating
            rating.updated_at = datetime.utcnow()
        else:
            rating = models.Rating(
                user_id=user.id,
                film_id=film.id,
                rating=payload.rating,
            )
            session.add(rating)
