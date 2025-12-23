from __future__ import annotations

from datetime import datetime
from typing import Iterable

from sqlalchemy.orm import Session

from ..db import models
from ..scrapers.rss import RSSEntry
from .cohorts import get_or_create_user
from .ratings import get_or_create_film


def apply_rss_entries(session: Session, username: str, entries: Iterable[RSSEntry]) -> int:
    """Update ratings table based on RSS entries."""
    user = get_or_create_user(session, username)
    updated = 0
    for entry in entries:
        film = get_or_create_film(session, entry.film_slug, entry.film_title)
        rating = session.get(models.Rating, {"user_id": user.id, "film_id": film.id})
        timestamp = entry.published or datetime.utcnow()
        if rating:
            rating.rating = entry.rating
            rating.updated_at = timestamp
        else:
            rating = models.Rating(
                user_id=user.id,
                film_id=film.id,
                rating=entry.rating,
                rated_at=timestamp,
                updated_at=timestamp,
            )
            session.add(rating)
        updated += 1
    return updated
