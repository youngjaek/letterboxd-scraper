from __future__ import annotations

from datetime import datetime
from typing import Iterable, Optional, Tuple, List, Union

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from ..db import models
from ..scrapers.follow_graph import FollowResult


def get_or_create_user(session: Session, username: str, display_name: Optional[str] = None) -> models.User:
    stmt = select(models.User).where(models.User.letterboxd_username == username)
    user = session.scalars(stmt).one_or_none()
    if user:
        if display_name and user.display_name != display_name:
            user.display_name = display_name
        return user
    user = models.User(letterboxd_username=username, display_name=display_name)
    session.add(user)
    session.flush()
    return user


def create_cohort(
    session: Session,
    seed_user: models.User,
    label: str,
    definition: Optional[dict] = None,
) -> models.Cohort:
    cohort = models.Cohort(label=label, seed_user_id=seed_user.id, definition=definition)
    session.add(cohort)
    session.flush()
    return cohort


def add_member(
    session: Session,
    cohort: models.Cohort,
    member_user: models.User,
    depth: int,
    followed_at: Optional[datetime] = None,
) -> models.CohortMember:
    member = models.CohortMember(
        cohort_id=cohort.id,
        user_id=member_user.id,
        depth=depth,
        followed_at=followed_at,
    )
    session.merge(member)
    return member


def list_cohorts(session: Session) -> List[Tuple[int, str, Optional[int], int]]:
    stmt = select(models.Cohort).options(joinedload(models.Cohort.members))
    cohorts = session.scalars(stmt).unique().all()
    return [(c.id, c.label, c.seed_user_id, len(c.members)) for c in cohorts]


def get_cohort(session: Session, cohort_id: int) -> Optional[models.Cohort]:
    return session.get(models.Cohort, cohort_id)


def rename_cohort(session: Session, cohort_id: int, new_label: str) -> Optional[models.Cohort]:
    cohort = session.get(models.Cohort, cohort_id)
    if not cohort:
        return None
    cohort.label = new_label
    cohort.updated_at = datetime.utcnow()
    return cohort


def delete_cohort(session: Session, cohort_id: int) -> bool:
    cohort = session.get(models.Cohort, cohort_id)
    if not cohort:
        return False
    session.query(models.ScrapeRun).filter(models.ScrapeRun.cohort_id == cohort_id).delete()
    session.delete(cohort)
    return True


def list_member_usernames(session: Session, cohort_id: int) -> list[str]:
    stmt = (
        select(models.User.letterboxd_username)
        .join(models.CohortMember, models.CohortMember.user_id == models.User.id)
        .where(models.CohortMember.cohort_id == cohort_id)
    )
    return [row[0] for row in session.execute(stmt)]


def refresh_cohort_members(
    session: Session,
    cohort: models.Cohort,
    edges: Iterable[Tuple[int, FollowResult]],
    *,
    include_seed: bool,
    seed_username: Optional[str],
) -> None:
    """Replace cohort members using provided follow graph edges."""
    session.query(models.CohortMember).filter(models.CohortMember.cohort_id == cohort.id).delete()
    if include_seed and seed_username:
        seed_user = get_or_create_user(session, seed_username)
        add_member(session, cohort, seed_user, depth=0)
    for depth, payload in edges:
        user = get_or_create_user(session, payload.username, payload.display_name)
        add_member(session, cohort, user, depth=depth)
