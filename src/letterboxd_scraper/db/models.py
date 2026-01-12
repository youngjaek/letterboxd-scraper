from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Dict, Optional

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    letterboxd_username: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    display_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    avatar_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    last_full_scrape_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_incremental_scrape_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    ratings: Mapped[list["Rating"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class Film(Base):
    __tablename__ = "films"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=False)
    letterboxd_film_id: Mapped[Optional[int]] = mapped_column(Integer, unique=True)
    letterboxd_rating_count: Mapped[Optional[int]] = mapped_column(Integer)
    letterboxd_fan_count: Mapped[Optional[int]] = mapped_column(Integer)
    letterboxd_weighted_average: Mapped[Optional[float]] = mapped_column(Numeric(4, 2))
    release_year: Mapped[Optional[int]] = mapped_column(Integer)
    release_date: Mapped[Optional[date]] = mapped_column(Date)
    tmdb_id: Mapped[Optional[int]] = mapped_column(Integer)
    tmdb_media_type: Mapped[Optional[str]] = mapped_column(String)
    tmdb_show_id: Mapped[Optional[int]] = mapped_column(Integer)
    tmdb_season_number: Mapped[Optional[int]] = mapped_column(Integer)
    tmdb_episode_number: Mapped[Optional[int]] = mapped_column(Integer)
    imdb_id: Mapped[Optional[str]] = mapped_column(String)
    runtime_minutes: Mapped[Optional[int]] = mapped_column(Integer)
    poster_url: Mapped[Optional[str]] = mapped_column(Text)
    overview: Mapped[Optional[str]] = mapped_column(Text)
    tmdb_synced_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    tmdb_not_found: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    ratings: Mapped[list["Rating"]] = relationship(back_populates="film", cascade="all, delete-orphan")
    people: Mapped[list["FilmPerson"]] = relationship(back_populates="film", cascade="all, delete-orphan")
    genres: Mapped[list["Genre"]] = relationship(
        "Genre", secondary="film_genres", back_populates="films", lazy="selectin"
    )
    countries: Mapped[list["Country"]] = relationship(
        "Country", secondary="film_countries", back_populates="films", lazy="selectin"
    )
    histograms: Mapped[list["FilmHistogram"]] = relationship(
        back_populates="film", cascade="all, delete-orphan"
    )


class Rating(Base):
    __tablename__ = "ratings"
    __table_args__ = (
        UniqueConstraint("user_id", "film_id", name="ratings_user_film_key"),
    )

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    film_id: Mapped[int] = mapped_column(ForeignKey("films.id", ondelete="CASCADE"), primary_key=True)
    rating: Mapped[Optional[float]] = mapped_column(Numeric(3, 1), nullable=True)
    rated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )
    diary_entry_url: Mapped[Optional[str]] = mapped_column(Text)
    liked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    favorite: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    user: Mapped["User"] = relationship(back_populates="ratings")
    film: Mapped["Film"] = relationship(back_populates="ratings")


class Genre(Base):
    __tablename__ = "genres"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tmdb_id: Mapped[int] = mapped_column(Integer, unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    films: Mapped[list["Film"]] = relationship(
        "Film", secondary="film_genres", back_populates="genres"
    )


class FilmGenre(Base):
    __tablename__ = "film_genres"

    film_id: Mapped[int] = mapped_column(
        ForeignKey("films.id", ondelete="CASCADE"), primary_key=True
    )
    genre_id: Mapped[int] = mapped_column(
        ForeignKey("genres.id", ondelete="CASCADE"), primary_key=True
    )


class Country(Base):
    __tablename__ = "countries"

    code: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[Optional[str]] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    films: Mapped[list["Film"]] = relationship(
        "Film", secondary="film_countries", back_populates="countries"
    )


class FilmCountry(Base):
    __tablename__ = "film_countries"

    film_id: Mapped[int] = mapped_column(
        ForeignKey("films.id", ondelete="CASCADE"), primary_key=True
    )
    country_code: Mapped[str] = mapped_column(
        ForeignKey("countries.code", ondelete="CASCADE"), primary_key=True
    )


class Person(Base):
    __tablename__ = "people"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tmdb_id: Mapped[Optional[int]] = mapped_column(Integer, unique=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    profile_url: Mapped[Optional[str]] = mapped_column(Text)
    known_for_department: Mapped[Optional[str]] = mapped_column(String)
    tmdb_synced_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    film_credits: Mapped[list["FilmPerson"]] = relationship(back_populates="person")


class Cohort(Base):
    __tablename__ = "cohorts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    label: Mapped[str] = mapped_column(String, nullable=False)
    seed_user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"))
    definition: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    members: Mapped[list["CohortMember"]] = relationship(back_populates="cohort", cascade="all, delete-orphan")


class CohortMember(Base):
    __tablename__ = "cohort_members"

    cohort_id: Mapped[int] = mapped_column(
        ForeignKey("cohorts.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    depth: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    followed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    cohort: Mapped["Cohort"] = relationship(back_populates="members")
    user: Mapped["User"] = relationship()


class ScrapeRun(Base):
    __tablename__ = "scrape_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    cohort_id: Mapped[Optional[int]] = mapped_column(ForeignKey("cohorts.id"))
    run_type: Mapped[str] = mapped_column(String, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    status: Mapped[Optional[str]] = mapped_column(String)
    notes: Mapped[Optional[str]] = mapped_column(Text)


class UserScrapeState(Base):
    __tablename__ = "user_scrape_state"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    last_page: Mapped[int] = mapped_column(Integer, default=1)
    last_cursor: Mapped[Optional[str]] = mapped_column(String)
    last_status: Mapped[Optional[str]] = mapped_column(String)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )


class FilmRanking(Base):
    __tablename__ = "film_rankings"

    cohort_id: Mapped[int] = mapped_column(
        ForeignKey("cohorts.id", ondelete="CASCADE"), primary_key=True
    )
    strategy: Mapped[str] = mapped_column(String, primary_key=True)
    film_id: Mapped[int] = mapped_column(
        ForeignKey("films.id", ondelete="CASCADE"), primary_key=True
    )
    score: Mapped[float] = mapped_column(Numeric, nullable=False)
    rank: Mapped[Optional[int]] = mapped_column(Integer)
    params: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class RankingInsight(Base):
    __tablename__ = "ranking_insights"

    cohort_id: Mapped[int] = mapped_column(
        ForeignKey("cohorts.id", ondelete="CASCADE"), primary_key=True
    )
    strategy: Mapped[str] = mapped_column(String, primary_key=True)
    film_id: Mapped[int] = mapped_column(
        ForeignKey("films.id", ondelete="CASCADE"), primary_key=True
    )
    timeframe_key: Mapped[str] = mapped_column(String, primary_key=True)
    filters: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON)
    watchers: Mapped[Optional[int]] = mapped_column(Integer)
    avg_rating: Mapped[Optional[float]] = mapped_column(Numeric)
    watchers_percentile: Mapped[Optional[float]] = mapped_column(Numeric)
    rating_percentile: Mapped[Optional[float]] = mapped_column(Numeric)
    watchers_zscore: Mapped[Optional[float]] = mapped_column(Numeric)
    rating_zscore: Mapped[Optional[float]] = mapped_column(Numeric)
    cluster_label: Mapped[Optional[str]] = mapped_column(String)
    bucket_label: Mapped[Optional[str]] = mapped_column(String)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class FilmPerson(Base):
    __tablename__ = "film_people"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    film_id: Mapped[int] = mapped_column(ForeignKey("films.id", ondelete="CASCADE"))
    person_id: Mapped[int] = mapped_column(ForeignKey("people.id", ondelete="CASCADE"))
    role: Mapped[str] = mapped_column(String, nullable=False)
    credit_order: Mapped[Optional[int]] = mapped_column(Integer)

    film: Mapped["Film"] = relationship(back_populates="people")
    person: Mapped["Person"] = relationship(back_populates="film_credits")


class JobRun(Base):
    __tablename__ = "job_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_name: Mapped[str] = mapped_column(String, nullable=False)
    cohort_id: Mapped[Optional[int]] = mapped_column(ForeignKey("cohorts.id"))
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"))
    status: Mapped[str] = mapped_column(String, nullable=False, default="pending")
    payload: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[Optional[str]] = mapped_column(Text)


class FilmHistogram(Base):
    __tablename__ = "film_histograms"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    film_id: Mapped[int] = mapped_column(ForeignKey("films.id", ondelete="CASCADE"))
    cohort_id: Mapped[Optional[int]] = mapped_column(ForeignKey("cohorts.id", ondelete="CASCADE"))
    bucket_label: Mapped[str] = mapped_column(String, nullable=False)
    count: Mapped[int] = mapped_column(Integer, nullable=False)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    film: Mapped["Film"] = relationship(back_populates="histograms")
