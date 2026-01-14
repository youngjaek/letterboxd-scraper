from __future__ import annotations

import math
from dataclasses import dataclass
from statistics import fmean, pstdev
from typing import Any, Dict, List, Optional, Sequence, Tuple

from sqlalchemy import bindparam, delete, text
from sqlalchemy.orm import Session

from ..db import models


@dataclass
class RankingResult:
    film_id: int
    score: float
    rank: int
    metadata: Dict[str, Any]


@dataclass
class RankedFilm:
    film_id: int
    rank: Optional[int]
    score: float
    slug: str
    title: str
    watchers: Optional[int]
    avg_rating: Optional[float]


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


def compute_cohort_affinity(
    session: Session,
    cohort_id: int,
    watchers_floor: int,
) -> List[RankingResult]:
    """
    Blend average rating, popularity, and enthusiasm metrics into a single score.
    """
    watchers_floor = max(1, watchers_floor)
    stmt = text(
        """
        SELECT
            film_id,
            watchers,
            avg_rating,
            COALESCE(likes_count, 0) AS likes_count,
            COALESCE(favorites_count, 0) AS favorites_count,
            COALESCE(high_rating_pct, 0) AS high_rating_pct,
            COALESCE(low_rating_pct, 0) AS low_rating_pct,
            COALESCE(count_rating_gte_4_5, 0) AS count_rating_gte_4_5,
            COALESCE(count_rating_4_0_4_5, 0) AS count_rating_4_0_4_5,
            COALESCE(count_rating_3_5_4_0, 0) AS count_rating_3_5_4_0,
            COALESCE(count_rating_3_0_3_5, 0) AS count_rating_3_0_3_5,
            COALESCE(count_rating_2_5_3_0, 0) AS count_rating_2_5_3_0,
            COALESCE(count_rating_lt_2_5, 0) AS count_rating_lt_2_5
        FROM cohort_film_stats
        WHERE cohort_id = :cohort_id
          AND watchers >= :watchers_floor
        """
    )
    rows = session.execute(
        stmt,
        {"cohort_id": cohort_id, "watchers_floor": watchers_floor},
    ).mappings().all()
    if not rows:
        return []
    avg_ratings = [float(row["avg_rating"]) if row["avg_rating"] is not None else 0.0 for row in rows]
    avg_rating_z = _z_scores(avg_ratings)

    log_watchers = [math.log10(max(1, int(row["watchers"]))) for row in rows]
    watchers_z = _z_scores(log_watchers)

    favorite_rates = [_safe_ratio(row["favorites_count"], row["watchers"]) for row in rows]
    favorite_rate_z = _z_scores(favorite_rates)

    like_rates = [_safe_ratio(row["likes_count"], row["watchers"]) for row in rows]
    like_rate_z = _z_scores(like_rates)

    consensus_strengths = [
        _clamp((row["high_rating_pct"] or 0) - (row["low_rating_pct"] or 0), -1.0, 1.0) for row in rows
    ]

    distributions = [
        classify_distribution_label(
            watchers=int(row["watchers"]),
            count_gte_4_5=int(row["count_rating_gte_4_5"]),
            count_4_0_4_5=int(row["count_rating_4_0_4_5"]),
            count_3_5_4_0=int(row["count_rating_3_5_4_0"]),
            count_3_0_3_5=int(row["count_rating_3_0_3_5"]),
            count_2_5_3_0=int(row["count_rating_2_5_3_0"]),
            count_lt_2_5=int(row["count_rating_lt_2_5"]),
        )
        for row in rows
    ]

    scored_rows: list[tuple[int, float, Dict[str, Any]]] = []
    for idx, row in enumerate(rows):
        distribution_label, distribution_bonus = distributions[idx]
        watchers_component = min(watchers_z[idx], 1.0)
        score = (
            0.35 * avg_rating_z[idx]
            + 0.20 * watchers_component
            + 0.25 * favorite_rate_z[idx]
            + 0.10 * like_rate_z[idx]
            + 0.10 * distribution_bonus
            + 0.10 * consensus_strengths[idx]
        )
        metadata: Dict[str, Any] = {
            "watchers": int(row["watchers"]),
            "avg_rating": float(row["avg_rating"]) if row["avg_rating"] is not None else None,
            "favorite_rate": favorite_rates[idx],
            "like_rate": like_rates[idx],
            "distribution_label": distribution_label,
            "consensus_strength": consensus_strengths[idx],
        }
        scored_rows.append((int(row["film_id"]), score, metadata))

    ordered = sorted(scored_rows, key=lambda entry: (-entry[1], -entry[2].get("watchers", 0)))
    results: List[RankingResult] = []
    for rank_idx, (film_id, score, metadata) in enumerate(ordered, start=1):
        results.append(
            RankingResult(
                film_id=film_id,
                score=score,
                rank=rank_idx,
                metadata=metadata,
            )
        )
    return results


def fetch_rankings_for_film_ids(
    session: Session,
    *,
    cohort_id: int,
    strategy: str,
    film_ids: Sequence[int],
) -> List[RankedFilm]:
    if not film_ids:
        return []
    stmt = text(
        """
        SELECT
            fr.film_id,
            fr.rank,
            fr.score,
            f.slug,
            f.title,
            stats.watchers,
            stats.avg_rating
        FROM film_rankings fr
        JOIN films f ON f.id = fr.film_id
        LEFT JOIN cohort_film_stats stats
            ON stats.cohort_id = fr.cohort_id AND stats.film_id = fr.film_id
        WHERE fr.cohort_id = :cohort_id
          AND fr.strategy = :strategy
          AND fr.film_id IN :film_ids
        ORDER BY fr.rank ASC
        """
    ).bindparams(bindparam("film_ids", expanding=True))
    rows = session.execute(
        stmt,
        {"cohort_id": cohort_id, "strategy": strategy, "film_ids": tuple(film_ids)},
    ).fetchall()
    ranked: List[RankedFilm] = []
    for row in rows:
        score = float(row.score) if row.score is not None else 0.0
        avg_rating = float(row.avg_rating) if row.avg_rating is not None else None
        watchers = int(row.watchers) if row.watchers is not None else None
        ranked.append(
            RankedFilm(
                film_id=row.film_id,
                rank=row.rank,
                score=score,
                slug=row.slug,
                title=row.title,
                watchers=watchers,
                avg_rating=avg_rating,
            )
        )
    return ranked


def persist_rankings(
    session: Session,
    cohort_id: int,
    strategy: str,
    results: Sequence[RankingResult],
    params: Dict[str, Any],
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


def _z_scores(values: Sequence[float]) -> List[float]:
    if not values:
        return []
    if len(values) == 1:
        return [0.0]
    mean_val = fmean(values)
    spread = pstdev(values)
    if spread == 0:
        return [0.0 for _ in values]
    return [(value - mean_val) / spread for value in values]


def _safe_ratio(numerator: float | int, denominator: float | int) -> float:
    denom = float(denominator)
    if denom <= 0:
        return 0.0
    return float(numerator) / denom


def classify_distribution_label(
    *,
    watchers: int,
    count_gte_4_5: int,
    count_4_0_4_5: int,
    count_3_5_4_0: int,
    count_3_0_3_5: int,
    count_2_5_3_0: int,
    count_lt_2_5: int,
) -> Tuple[str, float]:
    if watchers <= 0:
        return ("unknown", 0.0)
    w = float(watchers)
    pct_extreme = count_gte_4_5 / w
    pct_high = count_4_0_4_5 / w
    pct_mid_high = count_3_5_4_0 / w
    pct_mid_low = count_3_0_3_5 / w
    pct_low_mid = count_2_5_3_0 / w
    pct_low = count_lt_2_5 / w
    pct_high_total = pct_extreme + pct_high
    pct_low_total = pct_low_mid + pct_low

    if pct_extreme >= 0.4 and pct_low_total <= 0.1:
        return ("strong-left", 0.30)
    if pct_high_total >= 0.6 and pct_low_total <= 0.15:
        return ("left", 0.15)
    if pct_low_total >= 0.45 and pct_high_total <= 0.2:
        return ("right", -0.15)
    if pct_low_total >= 0.35 and pct_high_total >= 0.25:
        return ("bimodal-low-high", 0.05)
    if pct_mid_low >= 0.25 and pct_mid_high >= 0.25:
        return ("bimodal-mid", -0.05)
    if (pct_mid_high + pct_mid_low) >= 0.6 and pct_low_total <= 0.2:
        return ("balanced", 0.0)
    return ("mixed", 0.0)


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))
