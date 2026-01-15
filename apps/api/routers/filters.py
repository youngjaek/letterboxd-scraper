from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, Query
from sqlalchemy import distinct, select
from sqlalchemy.orm import Session

from letterboxd_scraper.db import models

from ..dependencies import get_db_session
from ..schemas import CountryOption, GenreOption, PersonOption


router = APIRouter(prefix="/filters", tags=["filters"])


def _apply_search_query(stmt, column, query: str | None):
    if query:
        pattern = f"%{query.strip()}%"
        return stmt.where(column.ilike(pattern))
    return stmt


@router.get("/genres", response_model=List[GenreOption], summary="Search genres")
def search_genres(
    q: str | None = None,
    ids: List[int] | None = Query(None),
    limit: int = 15,
    session: Session = Depends(get_db_session),
) -> list[GenreOption]:
    stmt = select(models.Genre.id, models.Genre.name).order_by(models.Genre.name.asc())
    if ids:
        stmt = stmt.where(models.Genre.id.in_(ids))
    else:
        stmt = _apply_search_query(stmt, models.Genre.name, q)
        stmt = stmt.limit(limit)
    rows = session.execute(stmt).all()
    return [GenreOption(id=row.id, name=row.name) for row in rows]


@router.get("/countries", response_model=List[CountryOption], summary="Search countries")
def search_countries(
    q: str | None = None,
    codes: List[str] | None = Query(None),
    limit: int = 15,
    session: Session = Depends(get_db_session),
) -> list[CountryOption]:
    stmt = select(models.Country.code, models.Country.name).order_by(models.Country.name.asc())
    if codes:
        normalized = [code.upper() for code in codes if code]
        stmt = stmt.where(models.Country.code.in_(normalized))
    else:
        stmt = _apply_search_query(stmt, models.Country.name, q)
        stmt = stmt.limit(limit)
    rows = session.execute(stmt).all()
    return [CountryOption(code=row.code, name=row.name) for row in rows]


@router.get("/directors", response_model=List[PersonOption], summary="Search directors")
def search_directors(
    q: str | None = None,
    ids: List[int] | None = Query(None),
    limit: int = 15,
    session: Session = Depends(get_db_session),
) -> list[PersonOption]:
    stmt = (
        select(distinct(models.Person.id).label("id"), models.Person.name)
        .join(models.FilmPerson, models.FilmPerson.person_id == models.Person.id)
        .where(models.FilmPerson.role == "director")
        .order_by(models.Person.name.asc())
    )
    if ids:
        stmt = stmt.where(models.Person.id.in_(ids))
    else:
        stmt = _apply_search_query(stmt, models.Person.name, q)
        stmt = stmt.limit(limit)
    rows = session.execute(stmt).all()
    return [PersonOption(id=row.id, name=row.name) for row in rows]
