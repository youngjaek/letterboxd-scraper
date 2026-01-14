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
    favorite_rate: float | None = None
    like_rate: float | None = None
    distribution_label: str | None = None
    consensus_strength: float | None = None
