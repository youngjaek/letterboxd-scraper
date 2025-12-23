from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Sequence

from sqlalchemy import delete, text
from sqlalchemy.orm import Session

from ..db import models


@dataclass
class RankingResult:
    film_id: int
    score: float
    rank: int
    metadata: Dict[str, float]


def compute_bayesian(session: Session, cohort_id: int, m_value: int) -> List[RankingResult]:
    """
    Placeholder bayesian ranking using SQL query aggregations.
    """
    query = text(
        """
        SELECT
            film_id,
            watchers,
            avg_rating,
            (watchers::float / (watchers + :m_value)) * avg_rating +
            ((CAST(:m_value AS float)) / (watchers + :m_value)) * cohort_avg AS score
        FROM cohort_film_stats
        CROSS JOIN (
            SELECT AVG(avg_rating) as cohort_avg
            FROM cohort_film_stats
            WHERE cohort_id = :cohort_id
        ) c
        WHERE cohort_id = :cohort_id
        ORDER BY score DESC
        """
    )
    rows = session.execute(query, {"cohort_id": cohort_id, "m_value": m_value}).fetchall()
    results: List[RankingResult] = []
    for idx, row in enumerate(rows, start=1):
        results.append(
            RankingResult(
                film_id=row.film_id,
                score=row.score,
                rank=idx,
                metadata={"watchers": row.watchers, "avg_rating": row.avg_rating},
            )
        )
    return results


def persist_rankings(
    session: Session,
    cohort_id: int,
    strategy: str,
    results: Sequence[RankingResult],
    params: Dict[str, float],
) -> None:
    session.execute(
        delete(models.FilmRanking).where(
            models.FilmRanking.cohort_id == cohort_id,
            models.FilmRanking.strategy == strategy,
        )
    )
    for result in results:
        session.add(
            models.FilmRanking(
                cohort_id=cohort_id,
                strategy=strategy,
                film_id=result.film_id,
                score=result.score,
                rank=result.rank,
                params=params,
            )
        )
