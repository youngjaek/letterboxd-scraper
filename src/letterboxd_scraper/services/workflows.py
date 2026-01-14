from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Set

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from ..config import Settings
from ..db import models
from ..db.session import get_session
from ..scrapers.follow_graph import FollowGraphScraper, expand_follow_graph
from ..scrapers.film_pages import FilmPageScraper
from ..scrapers.ratings import FilmRating, ProfileRatingsScraper
from . import cohorts as cohort_service
from . import insights as insight_service
from . import ratings as rating_service
from . import rankings as ranking_service
from . import stats as stats_service
from .enrichment import enrich_film_metadata, film_needs_enrichment
from .tmdb import TMDBClient


@dataclass
class UserScrapeResult:
    username: str
    fetched: int
    liked_only: int
    touched_film_ids: Set[int]
    incremental: bool
    entries: Optional[List[FilmRating]] = None


@dataclass
class CohortScrapeSummary:
    cohort_id: int
    requested_members: int
    processed_members: int
    total_entries: int
    touched_film_ids: Set[int]
    incremental: bool


@dataclass
class CohortRefreshResult:
    cohort_id: int
    depth: int
    include_seed: bool
    edges_discovered: int
    member_count: int


@dataclass
class RankingComputationResult:
    cohort_id: int
    strategy: str
    computed_rows: int


@dataclass
class BucketComputationResult:
    cohort_id: int
    strategy: str
    timeframe_key: str
    rows: int
    persisted: bool


@dataclass
class StatsRefreshResult:
    concurrently: bool


@dataclass
class EnrichmentResult:
    processed: int
    succeeded: int
    skipped: int
    film_ids: List[int]


def scrape_user_ratings(
    settings: Settings,
    username: str,
    *,
    incremental: bool = False,
    persist: bool = True,
    include_entries: bool = False,
) -> UserScrapeResult:
    """Fetch and persist a single user's ratings."""
    with get_session(settings) as session:
        snapshot = rating_service.get_user_rating_snapshot(session, username)
    scraper = ProfileRatingsScraper(settings)
    ratings: list[FilmRating] = []
    likes: list[FilmRating] = []
    profile_favorites: list[FilmRating] = []
    favorite_profile_slugs: Set[str] = set()
    try:
        profile_favorites = scraper.fetch_profile_favorites(username)
        favorite_profile_slugs = {
            entry.film_slug for entry in profile_favorites if entry.film_slug
        }
        for payload in scraper.fetch_user_ratings(username, favorite_slugs=favorite_profile_slugs):
            if rating_service.rating_matches_snapshot(snapshot, payload):
                break
            ratings.append(payload)
        rated_slugs = {item.film_slug for item in ratings}
        for payload in scraper.fetch_user_liked_films(username, favorite_slugs=favorite_profile_slugs):
            if payload.film_slug in rated_slugs:
                continue
            if rating_service.rating_matches_snapshot(snapshot, payload):
                break
            likes.append(payload)
    finally:
        scraper.close()
    likes_only = [item for item in likes if item.film_slug not in rated_slugs]
    combined = ratings + likes_only
    seen_slugs = {entry.film_slug for entry in combined if entry.film_slug}
    for favorite_entry in profile_favorites:
        slug = favorite_entry.film_slug
        if not slug or slug in seen_slugs:
            continue
        combined.append(favorite_entry)
        seen_slugs.add(slug)
    touched: Set[int] = set()
    if persist:
        with get_session(settings) as session:
            touched = rating_service.upsert_ratings(
                session,
                username,
                combined,
                touch_last_full=not incremental,
                touch_last_incremental=incremental,
                favorite_slugs=favorite_profile_slugs,
            )
    entries = combined if include_entries else None
    return UserScrapeResult(
        username=username,
        fetched=len(combined),
        liked_only=len(likes_only),
        touched_film_ids=touched,
        incremental=incremental,
        entries=entries,
    )


def scrape_cohort_members(
    settings: Settings,
    cohort_id: int,
    *,
    incremental: bool = True,
    member_limit: Optional[int] = None,
) -> CohortScrapeSummary:
    """Scrape ratings for every cohort member."""
    with get_session(settings) as session:
        stmt = (
            select(models.User.letterboxd_username)
            .join(models.CohortMember, models.CohortMember.user_id == models.User.id)
            .where(models.CohortMember.cohort_id == cohort_id)
            .order_by(models.CohortMember.depth.asc(), models.User.letterboxd_username.asc())
        )
        usernames = [row[0] for row in session.execute(stmt)]
    if not usernames:
        raise ValueError(f"Cohort {cohort_id} has no members to scrape.")
    requested = len(usernames)
    if member_limit is not None and member_limit >= 0:
        usernames = usernames[:member_limit]
    touched: Set[int] = set()
    total_entries = 0
    processed = 0
    for username in usernames:
        result = scrape_user_ratings(settings, username, incremental=incremental, persist=True)
        processed += 1
        total_entries += result.fetched
        touched.update(result.touched_film_ids)
    return CohortScrapeSummary(
        cohort_id=cohort_id,
        requested_members=requested,
        processed_members=processed,
        total_entries=total_entries,
        touched_film_ids=touched,
        incremental=incremental,
    )


def refresh_cohort_membership(settings: Settings, cohort_id: int) -> CohortRefreshResult:
    """Rebuild the follow-graph members for a cohort."""
    with get_session(settings) as session:
        cohort = cohort_service.get_cohort(session, cohort_id)
        if not cohort:
            raise ValueError(f"Cohort {cohort_id} not found.")
        definition = cohort.definition or {}
        depth = int(definition.get("depth", settings.cohort_defaults.follow_depth))
        include_seed = bool(definition.get("include_seed", settings.cohort_defaults.include_seed))
        seed_user = session.get(models.User, cohort.seed_user_id) if cohort.seed_user_id else None
        seed_username = seed_user.letterboxd_username if seed_user else None
        if not seed_username:
            raise ValueError("Cohort seed user missing a Letterboxd username.")
    scraper = FollowGraphScraper(settings)
    try:
        edges = list(expand_follow_graph(scraper, seed_username, depth))
    finally:
        scraper.close()
    with get_session(settings) as session:
        cohort = cohort_service.get_cohort(session, cohort_id)
        if not cohort:
            raise ValueError(f"Cohort {cohort_id} not found during refresh.")
        cohort_service.refresh_cohort_members(
            session,
            cohort,
            edges,
            include_seed=include_seed,
            seed_username=seed_username,
        )
        member_count = session.scalar(
            select(func.count()).select_from(models.CohortMember).where(models.CohortMember.cohort_id == cohort_id)
        )
    return CohortRefreshResult(
        cohort_id=cohort_id,
        depth=depth,
        include_seed=include_seed,
        edges_discovered=len(edges),
        member_count=int(member_count or 0),
    )


def refresh_stats(settings: Settings, *, concurrently: bool = False) -> StatsRefreshResult:
    with get_session(settings) as session:
        stats_service.refresh_cohort_stats(session, concurrently=concurrently)
    return StatsRefreshResult(concurrently=concurrently)


def compute_rankings(
    settings: Settings,
    cohort_id: int,
    *,
    strategy: str = "cohort_affinity",
) -> RankingComputationResult:
    with get_session(settings) as session:
        if strategy == "bayesian":
            m_value = settings.cohort_defaults.m_value
            results = ranking_service.compute_bayesian(session, cohort_id, m_value)
            params: Dict[str, float | Dict[str, float]] = {"m_value": float(m_value)}
        elif strategy == "cohort_affinity":
            watchers_floor = settings.cohort_defaults.affinity_watchers_floor
            results = ranking_service.compute_cohort_affinity(
                session,
                cohort_id,
                watchers_floor=watchers_floor,
            )
            params = {
                "watchers_floor": float(watchers_floor),
                "weights": {
                    "avg_rating": 0.35,
                    "watchers": 0.20,
                    "favorite_rate": 0.25,
                    "like_rate": 0.10,
                    "distribution_bonus": 0.10,
                    "consensus_strength": 0.10,
                },
            }
        else:
            raise ValueError(f"Unsupported ranking strategy '{strategy}'.")
        ranking_service.persist_rankings(
            session,
            cohort_id,
            strategy,
            results,
            params=params,
        )
    return RankingComputationResult(
        cohort_id=cohort_id,
        strategy=strategy,
        computed_rows=len(results),
    )


def compute_bucket_insights(
    settings: Settings,
    cohort_id: int,
    *,
    strategy: str = "bayesian",
    persist: bool = True,
) -> BucketComputationResult:
    with get_session(settings) as session:
        computation = insight_service.compute_ranking_buckets(session, cohort_id, strategy)
        if persist and computation.insights:
            insight_service.persist_insights(session, computation)
    return BucketComputationResult(
        cohort_id=cohort_id,
        strategy=strategy,
        timeframe_key=computation.timeframe_key,
        rows=len(computation.insights),
        persisted=bool(persist and computation.insights),
    )


def enrich_films(
    settings: Settings,
    *,
    film_ids: Optional[Sequence[int]] = None,
    limit: int = 50,
    force: bool = False,
) -> EnrichmentResult:
    """Enrich missing film metadata using TMDB + Letterboxd fallbacks."""
    with get_session(settings) as session:
        query = session.query(models.Film).options(selectinload(models.Film.people))
        if film_ids:
            query = query.filter(models.Film.id.in_(film_ids))
        else:
            query = query.filter(
                (models.Film.tmdb_id.is_(None))
                | (models.Film.poster_url.is_(None))
                | (models.Film.overview.is_(None))
                | (models.Film.release_year.is_(None))
            )
        films = query.limit(limit).all()
        film_id_list = [film.id for film in films]
    if not films:
        return EnrichmentResult(processed=0, succeeded=0, skipped=0, film_ids=[])
    client = TMDBClient(settings)
    film_page_scraper = FilmPageScraper(settings)
    succeeded = 0
    skipped = 0
    try:
        with get_session(settings) as session:
            for film_id in film_id_list:
                film = session.get(
                    models.Film,
                    film_id,
                    options=[selectinload(models.Film.people)],
                )
                if not film:
                    continue
                needs_enrichment = force or film_needs_enrichment(film)
                if not needs_enrichment:
                    skipped += 1
                    continue
                success = enrich_film_metadata(
                    session,
                    film,
                    client,
                    film_page_scraper=film_page_scraper,
                )
                if success:
                    succeeded += 1
    finally:
        film_page_scraper.close()
    processed = len(film_id_list)
    skipped = min(skipped, processed)
    return EnrichmentResult(
        processed=processed,
        succeeded=succeeded,
        skipped=skipped,
        film_ids=film_id_list,
    )
