from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session


def refresh_cohort_stats(session: Session, *, concurrently: bool = False) -> None:
    """Refresh materialized view storing cohort film stats."""
    if session.bind is None:
        raise RuntimeError("Session is not bound to an engine.")
    dialect = session.bind.dialect.name
    if dialect != "postgresql":
        raise NotImplementedError("Materialized view refresh supported only on PostgreSQL.")
    keyword = "CONCURRENTLY " if concurrently else ""
    session.execute(text(f"REFRESH MATERIALIZED VIEW {keyword}cohort_film_stats"))
