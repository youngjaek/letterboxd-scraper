from __future__ import annotations

from datetime import datetime, time, timezone
from typing import Iterable

from sqlalchemy.orm import Session

from ..db import models
from ..scrapers.rss import RSSEntry
from .cohorts import get_or_create_user
from .ratings import get_or_create_film


def apply_rss_entries(
    session: Session,
    username: str,
    entries: Iterable[RSSEntry],
) -> int:
    """Update ratings table based on RSS entries."""
    user = get_or_create_user(session, username)
    updated = 0
    rating_cache: dict[int, models.Rating] = {}
    for entry in entries:
        film = get_or_create_film(session, entry.film_slug, entry.film_title, entry.tmdb_id)
        rating = session.get(models.Rating, {"user_id": user.id, "film_id": film.id})
        if not rating:
            rating = rating_cache.get(film.id)
        timestamp = _rating_timestamp(entry)
        if rating:
            rating.rating = entry.rating
            if entry.watched_date:
                rating.rated_at = timestamp
            rating.updated_at = timestamp
            rating_cache[film.id] = rating
        else:
            rating = models.Rating(
                user_id=user.id,
                film_id=film.id,
                rating=entry.rating,
                rated_at=timestamp,
                updated_at=timestamp,
            )
            session.add(rating)
            rating_cache[film.id] = rating
        updated += 1
    return updated


def _rating_timestamp(entry: RSSEntry) -> datetime:
    if entry.watched_date:
        return datetime.combine(entry.watched_date, time.min, tzinfo=timezone.utc)
    if entry.published:
        return entry.published if entry.published.tzinfo else entry.published.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc)
