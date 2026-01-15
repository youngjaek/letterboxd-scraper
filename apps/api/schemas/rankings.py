from __future__ import annotations

from pydantic import BaseModel


class RatingHistogramBin(BaseModel):
    key: str
    label: str
    count: int


class DirectorCredit(BaseModel):
    id: int
    name: str


class RankingItem(BaseModel):
    film_id: int
    rank: int | None
    score: float
    title: str
    slug: str
    poster_url: str | None = None
    release_year: int | None = None
    watchers: int | None
    avg_rating: float | None
    favorite_rate: float | None = None
    like_rate: float | None = None
    distribution_label: str | None = None
    consensus_strength: float | None = None
    rating_histogram: list[RatingHistogramBin] = []
    directors: list[DirectorCredit] = []
    genres: list[str] = []


class RankingListResponse(BaseModel):
    items: list[RankingItem]
    total: int = 0


class GenreOption(BaseModel):
    id: int
    name: str


class CountryOption(BaseModel):
    code: str
    name: str | None = None


class PersonOption(BaseModel):
    id: int
    name: str
