from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session, joinedload

from letterboxd_scraper import config, services
from letterboxd_scraper.pipeline import tasks as pipeline_tasks
from letterboxd_scraper.db import models

from ..auth import require_api_user
from ..dependencies import get_db_session, get_settings
from ..schemas import (
    CohortCreateRequest,
    CohortDefinition,
    CohortDetail,
    CohortSummary,
    RankingItem,
)


router = APIRouter(prefix="/cohorts", tags=["cohorts"])


@router.get("/", response_model=List[CohortSummary], summary="List cohorts")
def list_cohorts(session: Session = Depends(get_db_session)) -> list[CohortSummary]:
    stmt = (
        select(
            models.Cohort.id,
            models.Cohort.label,
            models.Cohort.seed_user_id,
            models.Cohort.created_at,
            models.Cohort.updated_at,
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
        )
        for row in results
    ]


@router.get("/{cohort_id}", response_model=CohortDetail, summary="Cohort details")
def get_cohort_detail(cohort_id: int, session: Session = Depends(get_db_session)) -> CohortDetail:
    stmt = (
        select(models.Cohort)
        .options(joinedload(models.Cohort.members).joinedload(models.CohortMember.user))
        .where(models.Cohort.id == cohort_id)
    )
    cohort = session.scalars(stmt).unique().one_or_none()
    if not cohort:
        raise HTTPException(status_code=404, detail="Cohort not found")
    member_usernames = [member.user.letterboxd_username for member in cohort.members]
    definition_payload = cohort.definition if isinstance(cohort.definition, dict) else None
    definition = CohortDefinition.model_validate(definition_payload) if definition_payload else None
    return CohortDetail(
        id=cohort.id,
        label=cohort.label,
        seed_user_id=cohort.seed_user_id,
        member_count=len(member_usernames),
        created_at=cohort.created_at,
        updated_at=cohort.updated_at,
        definition=definition,
        members=member_usernames,
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


@router.get("/{cohort_id}/rankings", response_model=List[RankingItem], summary="Top rankings")
def list_rankings(
    cohort_id: int,
    strategy: str = "bayesian",
    limit: int = 25,
    session: Session = Depends(get_db_session),
) -> list[RankingItem]:
    stmt = text(
        """
        SELECT
            fr.film_id,
            fr.rank,
            fr.score,
            f.title,
            f.slug,
            stats.watchers,
            stats.avg_rating
        FROM film_rankings fr
        JOIN films f ON f.id = fr.film_id
        LEFT JOIN cohort_film_stats stats
            ON stats.cohort_id = fr.cohort_id AND stats.film_id = fr.film_id
        WHERE fr.cohort_id = :cohort_id
          AND fr.strategy = :strategy
        ORDER BY fr.rank ASC
        LIMIT :limit
        """
    )
    rows = session.execute(
        stmt,
        {"cohort_id": cohort_id, "strategy": strategy, "limit": limit},
    ).fetchall()
    return [
        RankingItem(
            film_id=row.film_id,
            rank=row.rank,
            score=float(row.score) if row.score is not None else 0.0,
            title=row.title,
            slug=row.slug,
            watchers=int(row.watchers) if row.watchers is not None else None,
            avg_rating=float(row.avg_rating) if row.avg_rating is not None else None,
        )
        for row in rows
    ]


@router.post("/{cohort_id}/sync", summary="Run cohort pipeline")
def trigger_cohort_sync(
    cohort_id: int,
    incremental: bool = True,
    user: models.User = Depends(require_api_user),
) -> dict:
    result = pipeline_tasks.run_cohort_pipeline.delay(cohort_id, incremental=incremental)
    return {"task_id": result.id, "cohort_id": cohort_id, "incremental": incremental}


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
