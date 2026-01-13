from __future__ import annotations

from pydantic import BaseModel


class RankingItem(BaseModel):
    film_id: int
    rank: int | None
    score: float
    title: str
    slug: str
    watchers: int | None
    avg_rating: float | None
