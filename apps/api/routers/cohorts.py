from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from letterboxd_scraper.db import models

from ..dependencies import get_db_session
from ..schemas import CohortDefinition, CohortDetail, CohortSummary


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
    definition = (
        CohortDefinition.model_validate(definition_payload)
        if definition_payload
        else None
    )
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
