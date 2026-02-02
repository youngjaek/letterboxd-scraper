from __future__ import annotations

from datetime import datetime
from typing import List
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc, func, select, text
from sqlalchemy.orm import Session, joinedload

from letterboxd_scraper import config, services
from letterboxd_scraper.pipeline import tasks as pipeline_tasks
from letterboxd_scraper.db import models
from letterboxd_scraper.scrapers.listings import FilmListEntry, PosterListingScraper
from ..auth import require_api_user
from ..dependencies import get_db_session, get_settings
from ..schemas import (
    CohortCreateRequest,
    CohortDefinition,
    CohortDetail,
    CohortMemberProfile,
    CohortSummary,
    RankingItem,
    RankingListResponse,
    ScrapeMemberStatus,
    ScrapeProgress,
)


router = APIRouter(prefix="/cohorts", tags=["cohorts"])

DISTRIBUTION_LABELS = [
    "unknown",
    "five-star-dominant",
    "mixed",
]

RESULT_LIMIT_OPTIONS = [100, 250, 500, 1000]

SORTABLE_FIELDS: dict[str, str] = {
    "score": "score",
    "watchers": "watchers",
    "release_year": "release_year",
    "avg_rating": "avg_rating",
}
DEFAULT_SORT_BY = "score"
DEFAULT_SORT_ORDER = "desc"
SORT_ORDER_VALUES = {"asc", "desc"}


def _extract_letterboxd_film_ids(
    source_url: str,
    session: Session,
    settings: config.Settings,
) -> list[int]:
    if not source_url:
        return []
    scraper = PosterListingScraper(settings)
    entries: list[FilmListEntry] = []
    try:
        entries = list(scraper.iter_list_entries(source_url))
        if not entries:
            entries = list(scraper.iter_single_page(source_url))
        if not entries and _looks_like_collection_path(source_url):
            entries = _fetch_collection_entries(scraper, source_url)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=400, detail=f"Failed to load Letterboxd source: {exc}") from exc
    finally:
        scraper.close()
    if not entries:
        raise HTTPException(status_code=400, detail="No films detected in the provided Letterboxd URL.")
    slugs = [entry.slug for entry in entries if entry.slug]
    if not slugs:
        raise HTTPException(status_code=400, detail="No film slugs detected in the provided Letterboxd URL.")
    film_rows = (
        session.query(models.Film.id, models.Film.slug)
        .filter(models.Film.slug.in_(slugs))
        .all()
    )
    film_by_slug = {row.slug: int(row.id) for row in film_rows}
    ordered_ids: list[int] = []
    seen_ids: set[int] = set()
    for slug in slugs:
        film_id = film_by_slug.get(slug)
        if not film_id or film_id in seen_ids:
            continue
        seen_ids.add(film_id)
        ordered_ids.append(film_id)
    if not ordered_ids:
        raise HTTPException(
            status_code=404,
            detail="None of the films from the provided Letterboxd URL exist in this database.",
        )
    return ordered_ids


def _normalize_letterboxd_url(value: str) -> str:
    raw = (value or "").strip()
    if not raw:
        return ""
    if not raw.startswith(("http://", "https://")):
        raw = f"https://letterboxd.com/{raw.lstrip('/')}"
    parsed = urlparse(raw)
    scheme = parsed.scheme or "https"
    netloc = parsed.netloc or "letterboxd.com"
    path = parsed.path or "/"
    if not path.startswith("/"):
        path = "/" + path
    if not path.endswith("/"):
        path += "/"
    query = f"?{parsed.query}" if parsed.query else ""
    return f"{scheme}://{netloc}{path}{query}"


def _looks_like_collection_path(value: str) -> bool:
    normalized = _normalize_letterboxd_url(value)
    if not normalized:
        return False
    parsed = urlparse(normalized)
    segments = [segment for segment in parsed.path.strip("/").split("/") if segment]
    return len(segments) >= 3 and segments[0] == "films" and segments[1] == "in"


def _fetch_collection_entries(scraper: PosterListingScraper, source_url: str) -> list[FilmListEntry]:
    normalized = _normalize_letterboxd_url(source_url)
    if not normalized:
        return []
    parsed = urlparse(normalized)
    segments = [segment for segment in parsed.path.strip("/").split("/") if segment]
    if len(segments) < 3 or segments[0] != "films" or segments[1] != "in":
        return []
    while len(segments) >= 2 and segments[-2] == "page" and segments[-1].isdigit():
        segments = segments[:-2]
    remainder = "/".join(segments[1:])
    base = f"{parsed.scheme or 'https'}://{parsed.netloc or 'letterboxd.com'}"
    query = f"?{parsed.query}" if parsed.query else ""
    collected: list[FilmListEntry] = []
    page = 1
    while True:
        ajax_url = f"{base}/films/ajax/{remainder}/page/{page}/"
        if query:
            ajax_url = f"{ajax_url}{query}"
        try:
            response = scraper.client.get(ajax_url)
        except httpx.HTTPStatusError as exc:
            if page > 1 and exc.response.status_code == 404:
                break
            raise
        chunk = PosterListingScraper.parse_html(response.text)
        if not chunk:
            break
        collected.extend(chunk)
        page += 1
    return collected


DISTRIBUTION_LABEL_SQL = """
CASE
    WHEN COALESCE(stats.watchers, 0) > 0
        AND (
            COALESCE(stats.count_rating_5_0, 0)::float / NULLIF(stats.watchers::float, 0)
        ) >= 0.4
        AND (
            GREATEST(
                COALESCE(stats.count_rating_4_5, 0),
                COALESCE(stats.count_rating_4_0, 0),
                COALESCE(stats.count_rating_3_5, 0),
                COALESCE(stats.count_rating_3_0, 0),
                COALESCE(stats.count_rating_2_5, 0),
                COALESCE(stats.count_rating_2_0, 0),
                COALESCE(stats.count_rating_1_5, 0),
                COALESCE(stats.count_rating_1_0, 0),
                COALESCE(stats.count_rating_0_5, 0)
            )::float / NULLIF(stats.watchers::float, 0)
        ) <= (
            COALESCE(stats.count_rating_5_0, 0)::float / NULLIF(stats.watchers::float, 0)
        ) / 2
    THEN 'five-star-dominant'
    WHEN COALESCE(stats.watchers, 0) <= 0 THEN 'unknown'
    ELSE 'mixed'
END
""".strip()


@router.get("/", response_model=List[CohortSummary], summary="List cohorts")
def list_cohorts(session: Session = Depends(get_db_session)) -> list[CohortSummary]:
    stmt = (
        select(
            models.Cohort.id,
            models.Cohort.label,
            models.Cohort.seed_user_id,
            models.Cohort.created_at,
            models.Cohort.updated_at,
            models.Cohort.current_task_id,
            func.count(models.CohortMember.user_id).label("member_count"),
        )
        .outerjoin(models.CohortMember, models.CohortMember.cohort_id == models.Cohort.id)
        .group_by(models.Cohort.id)
        .order_by(models.Cohort.created_at.desc())
    )
    results = session.execute(stmt).all()
    return [
        CohortSummary(
            id=row.id,
            label=row.label,
            seed_user_id=row.seed_user_id,
            member_count=row.member_count,
            created_at=row.created_at,
            updated_at=row.updated_at,
            current_task_id=row.current_task_id,
        )
        for row in results
    ]


@router.get("/{cohort_id}", response_model=CohortDetail, summary="Cohort details")
def get_cohort_detail(cohort_id: int, session: Session = Depends(get_db_session)) -> CohortDetail:
    stmt = (
        select(models.Cohort)
        .options(
            joinedload(models.Cohort.members).joinedload(models.CohortMember.user),
        )
        .where(models.Cohort.id == cohort_id)
    )
    cohort = session.scalars(stmt).unique().one_or_none()
    if not cohort:
        raise HTTPException(status_code=404, detail="Cohort not found")
    member_profiles = [
        CohortMemberProfile(
            username=member.user.letterboxd_username,
            avatar_url=member.user.avatar_url,
        )
        for member in cohort.members
    ]
    definition_payload = cohort.definition if isinstance(cohort.definition, dict) else None
    definition = CohortDefinition.model_validate(definition_payload) if definition_payload else None
    seed_username = None
    if cohort.seed_user_id:
        seed_user = session.get(models.User, cohort.seed_user_id)
        seed_username = seed_user.letterboxd_username if seed_user else None
    return CohortDetail(
        id=cohort.id,
        label=cohort.label,
        seed_user_id=cohort.seed_user_id,
        seed_username=seed_username,
        member_count=len(member_profiles),
        created_at=cohort.created_at,
        updated_at=cohort.updated_at,
        current_task_id=cohort.current_task_id,
        definition=definition,
        members=member_profiles,
    )


@router.get("/{cohort_id}/scrape-status", response_model=ScrapeProgress, summary="Scrape progress")
def get_scrape_status(cohort_id: int, session: Session = Depends(get_db_session)) -> ScrapeProgress:
    run_stmt = (
        select(models.ScrapeRun)
        .where(models.ScrapeRun.cohort_id == cohort_id)
        .order_by(desc(models.ScrapeRun.started_at))
        .limit(1)
    )
    run = session.scalars(run_stmt).one_or_none()
    if not run:
        return ScrapeProgress(status="idle")
    members_stmt = (
        select(models.ScrapeRunMember)
        .where(models.ScrapeRunMember.run_id == run.id)
        .order_by(models.ScrapeRunMember.username.asc())
    )
    members = session.scalars(members_stmt).all()
    total_members = len(members)
    completed = sum(1 for member in members if member.status == "done")
    failed = sum(1 for member in members if member.status == "failed")
    queued = sum(1 for member in members if member.status == "queued")
    in_progress = [
        ScrapeMemberStatus(
            username=member.username,
            status=member.status,
            mode=member.mode,
            started_at=member.started_at,
            finished_at=member.finished_at,
            error=member.error,
        )
        for member in members
        if member.status == "scraping"
    ]
    recent_finished = [
        ScrapeMemberStatus(
            username=member.username,
            status=member.status,
            mode=member.mode,
            started_at=member.started_at,
            finished_at=member.finished_at,
            error=member.error,
        )
        for member in members
        if member.status in {"done", "failed"}
    ]
    recent_finished.sort(key=lambda item: item.finished_at or item.started_at or datetime.min, reverse=True)
    recent_finished = recent_finished[:5]
    status = run.status or ("running" if in_progress or queued else "done")
    return ScrapeProgress(
        status=status,
        run_id=run.id,
        run_type=run.run_type,
        started_at=run.started_at,
        finished_at=run.finished_at,
        total_members=total_members,
        completed=completed,
        failed=failed,
        queued=queued,
        in_progress=in_progress,
        recent_finished=recent_finished,
    )


@router.post(
    "/",
    response_model=CohortDetail,
    status_code=status.HTTP_201_CREATED,
    summary="Create cohort",
)
def create_cohort(
    payload: CohortCreateRequest,
    session: Session = Depends(get_db_session),
    settings: config.Settings = Depends(get_settings),
    user: models.User = Depends(require_api_user),
) -> CohortDetail:
    definition = {
        "depth": payload.depth or settings.cohort_defaults.follow_depth,
        "include_seed": (
            payload.include_seed
            if payload.include_seed is not None
            else settings.cohort_defaults.include_seed
        ),
    }
    seed_user = services.cohorts.get_or_create_user(session, payload.seed_username)
    cohort = services.cohorts.create_cohort(session, seed_user, payload.label, definition)
    if definition["include_seed"]:
        services.cohorts.add_member(session, cohort, seed_user, depth=0)
    return get_cohort_detail(cohort.id, session=session)


@router.get(
    "/{cohort_id}/rankings",
    response_model=RankingListResponse,
    summary="Top rankings",
)
def list_rankings(
    cohort_id: int,
    strategy: str = "bayesian",
    limit: int = 50,
    page: int = 1,
    result_limit: int = Query(250),
    sort_by: str = Query(DEFAULT_SORT_BY),
    sort_order: str = Query(DEFAULT_SORT_ORDER),
    letterboxd_source: str | None = Query(
        None,
        description="Letterboxd list/filmography URL (or path) used to filter rankings to matching films.",
    ),
    genres: List[int] | None = Query(None),
    countries: List[str] | None = Query(None),
    directors: List[int] | None = Query(None),
    distribution: str | None = Query(None),
    release_year_min: int | None = None,
    release_year_max: int | None = None,
    decade: int | None = None,
    watchers_min: int | None = Query(2, ge=0),
    watchers_max: int | None = Query(None, ge=0),
    session: Session = Depends(get_db_session),
    settings: config.Settings = Depends(get_settings),
) -> RankingListResponse:
    limit = max(1, min(limit, result_limit, 1000))
    page = max(1, page)
    offset = (page - 1) * limit
    if result_limit not in RESULT_LIMIT_OPTIONS:
        raise HTTPException(
            status_code=400,
            detail=f"result_limit must be one of {', '.join(str(value) for value in RESULT_LIMIT_OPTIONS)}",
        )
    normalized_sort_by = sort_by.lower()
    sort_field = SORTABLE_FIELDS.get(normalized_sort_by)
    if not sort_field:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid sort_by '{sort_by}'. Allowed: {', '.join(SORTABLE_FIELDS.keys())}",
        )
    normalized_sort_order = sort_order.lower()
    if normalized_sort_order not in SORT_ORDER_VALUES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid sort_order '{sort_order}'. Allowed: {', '.join(SORT_ORDER_VALUES)}",
        )
    order_direction = "ASC" if normalized_sort_order == "asc" else "DESC"
    order_clause = f"{sort_field} {order_direction} NULLS LAST, filtered_rank ASC"
    params: dict[str, object] = {
        "cohort_id": cohort_id,
        "strategy": strategy,
        "limit": limit,
        "offset": offset,
        "result_limit": result_limit,
    }
    filter_clauses: list[str] = []
    if genres:
        genre_ids = list({int(value) for value in genres if value is not None})
        if genre_ids:
            params["genre_ids"] = genre_ids
            filter_clauses.append(
                "EXISTS (SELECT 1 FROM film_genres fg WHERE fg.film_id = fr.film_id AND fg.genre_id = ANY(:genre_ids))"
            )
    if countries:
        country_codes = list({code.upper() for code in countries if code})
        if country_codes:
            params["country_codes"] = country_codes
            filter_clauses.append(
                "EXISTS (SELECT 1 FROM film_countries fc WHERE fc.film_id = fr.film_id AND fc.country_code = ANY(:country_codes))"
            )
    if directors:
        director_ids = list({int(value) for value in directors if value is not None})
        if director_ids:
            params["director_ids"] = director_ids
            filter_clauses.append(
                "EXISTS (SELECT 1 FROM film_people fp WHERE fp.film_id = fr.film_id AND fp.role = 'director' AND fp.person_id = ANY(:director_ids))"
            )
    if distribution:
        normalized_label = distribution.strip().lower()
        if not normalized_label:
            raise HTTPException(status_code=400, detail="Distribution label cannot be empty.")
        if normalized_label not in DISTRIBUTION_LABELS:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid distribution label '{distribution}'. Allowed: {', '.join(DISTRIBUTION_LABELS)}",
            )
        params["distribution_label"] = normalized_label
        filter_clauses.append(f"({DISTRIBUTION_LABEL_SQL}) = :distribution_label")
    if release_year_min is not None:
        params["release_year_min"] = release_year_min
        filter_clauses.append("f.release_year >= :release_year_min")
    if release_year_max is not None:
        params["release_year_max"] = release_year_max
        filter_clauses.append("f.release_year <= :release_year_max")
    if decade is not None:
        decade_start = (decade // 10) * 10
        decade_end = decade_start + 9
        params["decade_start"] = decade_start
        params["decade_end"] = decade_end
        filter_clauses.append("f.release_year BETWEEN :decade_start AND :decade_end")
    if watchers_min is not None:
        if watchers_min < 0:
            raise HTTPException(status_code=400, detail="watchers_min cannot be negative.")
        params["watchers_min"] = watchers_min
        filter_clauses.append("COALESCE(stats.watchers, 0) >= :watchers_min")
    if watchers_max is not None:
        if watchers_max < 0:
            raise HTTPException(status_code=400, detail="watchers_max cannot be negative.")
        if watchers_min is not None and watchers_min > watchers_max:
            raise HTTPException(
                status_code=400, detail="watchers_min cannot be greater than watchers_max."
            )
        params["watchers_max"] = watchers_max
        filter_clauses.append("COALESCE(stats.watchers, 0) <= :watchers_max")
    if letterboxd_source:
        filter_film_ids = _extract_letterboxd_film_ids(letterboxd_source, session, settings)
        params["filter_film_ids"] = filter_film_ids
        filter_clauses.append("fr.film_id = ANY(:filter_film_ids)")
    filters_sql = ""
    if filter_clauses:
        filters_sql = " AND " + " AND ".join(filter_clauses)
    total_stmt = text(
        f"""
        WITH ranked AS (
            SELECT
                ROW_NUMBER() OVER (ORDER BY fr.rank ASC) AS filtered_rank
            FROM film_rankings fr
            JOIN films f ON f.id = fr.film_id
            LEFT JOIN cohort_film_stats stats
                ON stats.cohort_id = fr.cohort_id AND stats.film_id = fr.film_id
            WHERE fr.cohort_id = :cohort_id
              AND fr.strategy = :strategy
            {filters_sql}
        )
        SELECT COUNT(*)
        FROM ranked
        WHERE filtered_rank <= :result_limit
        """
    )
    total = session.execute(total_stmt, params).scalar_one()
    data_stmt = text(
        f"""
        WITH ranked AS (
            SELECT
                fr.film_id,
                fr.rank,
                fr.score,
                f.title,
                f.slug,
                f.poster_url,
                f.release_year,
                stats.watchers,
                stats.avg_rating,
                stats.likes_count,
                stats.favorites_count,
                stats.high_rating_pct,
                stats.low_rating_pct,
                stats.count_rating_gte_4_5,
                stats.count_rating_4_0_4_5,
                stats.count_rating_3_5_4_0,
                stats.count_rating_3_0_3_5,
                stats.count_rating_2_5_3_0,
                stats.count_rating_lt_2_5,
                stats.count_rating_0_5 AS count_0_5,
                stats.count_rating_1_0 AS count_1_0,
                stats.count_rating_1_5 AS count_1_5,
                stats.count_rating_2_0 AS count_2_0,
                stats.count_rating_2_5 AS count_2_5,
                stats.count_rating_3_0 AS count_3_0,
                stats.count_rating_3_5 AS count_3_5,
                stats.count_rating_4_0 AS count_4_0,
                stats.count_rating_4_5 AS count_4_5,
                stats.count_rating_5_0 AS count_5_0,
                {DISTRIBUTION_LABEL_SQL} AS distribution_label,
                COALESCE(genre_data.genres, ARRAY[]::text[]) AS genres,
                COALESCE(director_data.names, ARRAY[]::text[]) AS director_names,
                COALESCE(director_data.ids, ARRAY[]::int[]) AS director_ids,
                ROW_NUMBER() OVER (ORDER BY fr.rank ASC) AS filtered_rank
            FROM film_rankings fr
            JOIN films f ON f.id = fr.film_id
            LEFT JOIN cohort_film_stats stats
                ON stats.cohort_id = fr.cohort_id AND stats.film_id = fr.film_id
            LEFT JOIN LATERAL (
                SELECT array_remove(array_agg(g.name ORDER BY g.name), NULL) AS genres
                FROM film_genres fg
                JOIN genres g ON g.id = fg.genre_id
                WHERE fg.film_id = fr.film_id
            ) AS genre_data ON TRUE
            LEFT JOIN LATERAL (
                SELECT
                    array_remove(
                        array_agg(p.name ORDER BY COALESCE(fp.credit_order, 1000), p.name),
                        NULL
                    ) AS names,
                    array_remove(
                        array_agg(p.id ORDER BY COALESCE(fp.credit_order, 1000), p.name),
                        NULL
                    ) AS ids
                FROM film_people fp
                JOIN people p ON p.id = fp.person_id
                WHERE fp.film_id = fr.film_id AND fp.role = 'director'
            ) AS director_data ON TRUE
            WHERE fr.cohort_id = :cohort_id
              AND fr.strategy = :strategy
            {filters_sql}
        )
        SELECT *
        FROM ranked
        WHERE filtered_rank <= :result_limit
        ORDER BY {order_clause}
        OFFSET :offset
        LIMIT :limit
        """
    )
    rows = session.execute(data_stmt, params).fetchall()
    items: list[RankingItem] = []
    for row in rows:
        watchers = int(row.watchers) if row.watchers is not None else None
        avg_rating = float(row.avg_rating) if row.avg_rating is not None else None
        favorite_rate = None
        like_rate = None
        distribution_label = row.distribution_label
        consensus_strength = None
        if watchers and watchers > 0:
            favorite_rate = float(row.favorites_count or 0) / watchers
            like_rate = float(row.likes_count or 0) / watchers
        if row.high_rating_pct is not None and row.low_rating_pct is not None:
            strength = float(row.high_rating_pct) - float(row.low_rating_pct)
            consensus_strength = max(-1.0, min(1.0, strength))
        release_year = int(row.release_year) if row.release_year is not None else None
        histogram = [
            {"key": "0_5", "label": "½★", "count": int(row.count_0_5 or 0)},
            {"key": "1_0", "label": "1★", "count": int(row.count_1_0 or 0)},
            {"key": "1_5", "label": "1½★", "count": int(row.count_1_5 or 0)},
            {"key": "2_0", "label": "2★", "count": int(row.count_2_0 or 0)},
            {"key": "2_5", "label": "2½★", "count": int(row.count_2_5 or 0)},
            {"key": "3_0", "label": "3★", "count": int(row.count_3_0 or 0)},
            {"key": "3_5", "label": "3½★", "count": int(row.count_3_5 or 0)},
            {"key": "4_0", "label": "4★", "count": int(row.count_4_0 or 0)},
            {"key": "4_5", "label": "4½★", "count": int(row.count_4_5 or 0)},
            {"key": "5_0", "label": "5★", "count": int(row.count_5_0 or 0)},
        ]
        genres = [value for value in (row.genres or []) if value]
        director_names = list(row.director_names or [])
        director_ids = list(row.director_ids or [])
        directors: list[dict[str, object]] = []
        for name, director_id in zip(director_names, director_ids):
            if name and director_id is not None:
                directors.append({"name": name, "id": int(director_id)})
        items.append(
            RankingItem(
                film_id=row.film_id,
                rank=row.rank,
                score=float(row.score) if row.score is not None else 0.0,
                title=row.title,
                slug=row.slug,
                poster_url=row.poster_url,
                release_year=release_year,
                watchers=watchers,
                avg_rating=avg_rating,
                favorite_rate=favorite_rate,
                like_rate=like_rate,
                distribution_label=distribution_label,
                consensus_strength=consensus_strength,
                rating_histogram=histogram,
                directors=directors,
                genres=genres,
            )
        )
    return RankingListResponse(items=items, total=int(total))


@router.post("/{cohort_id}/sync", summary="Run cohort pipeline")
def trigger_cohort_sync(
    cohort_id: int,
    incremental: bool = True,
    session: Session = Depends(get_db_session),
    user: models.User = Depends(require_api_user),
) -> dict:
    cohort = session.get(models.Cohort, cohort_id)
    if not cohort:
        raise HTTPException(status_code=404, detail="Cohort not found")
    if cohort.current_task_id:
        raise HTTPException(status_code=409, detail="Cohort already syncing")
    result = pipeline_tasks.run_cohort_pipeline.delay(cohort_id, incremental=incremental)
    cohort.current_task_id = result.id
    session.commit()
    return {"task_id": result.id, "cohort_id": cohort_id, "incremental": incremental}


@router.post("/{cohort_id}/sync/stop", summary="Stop running cohort pipeline")
def stop_cohort_sync(
    cohort_id: int,
    session: Session = Depends(get_db_session),
    user: models.User = Depends(require_api_user),
) -> dict:
    cohort = session.get(models.Cohort, cohort_id)
    if not cohort:
        raise HTTPException(status_code=404, detail="Cohort not found")
    task_id = cohort.current_task_id
    if not task_id:
        raise HTTPException(status_code=409, detail="No active sync")
    pipeline_tasks.celery_app.control.revoke(task_id, terminate=True, signal="SIGTERM")
    cohort.current_task_id = None
    session.commit()
    return {"stopped_task_id": task_id, "cohort_id": cohort_id}


@router.patch("/{cohort_id}", response_model=CohortDetail, summary="Rename cohort")
def rename_cohort(
    cohort_id: int,
    label: str,
    session: Session = Depends(get_db_session),
    user: models.User = Depends(require_api_user),
) -> CohortDetail:
    cohort = services.cohorts.rename_cohort(session, cohort_id, label)
    if not cohort:
        raise HTTPException(status_code=404, detail="Cohort not found")
    return get_cohort_detail(cohort_id, session=session)


@router.delete("/{cohort_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete cohort")
def delete_cohort(
    cohort_id: int,
    session: Session = Depends(get_db_session),
    user: models.User = Depends(require_api_user),
) -> None:
    deleted = services.cohorts.delete_cohort(session, cohort_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Cohort not found")
