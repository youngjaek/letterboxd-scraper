from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from letterboxd_scraper.db import models

from ..dependencies import get_db_session
from ..schemas import CohortSummary


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
