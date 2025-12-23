from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Dict

from sqlalchemy import text
from sqlalchemy.orm import Session


def export_rankings_to_csv(
    session: Session,
    *,
    cohort_id: int,
    strategy: str,
    min_score: float,
    output_path: Path,
) -> int:
    query = text(
        """
        SELECT fr.rank, fr.score, f.title, f.slug, stats.watchers, stats.avg_rating
        FROM film_rankings fr
        JOIN films f ON f.id = fr.film_id
        LEFT JOIN cohort_film_stats stats
            ON stats.cohort_id = fr.cohort_id AND stats.film_id = fr.film_id
        WHERE fr.cohort_id = :cohort_id
          AND fr.strategy = :strategy
          AND fr.score >= :min_score
        ORDER BY fr.rank ASC
        """
    )
    rows = session.execute(
        query, {"cohort_id": cohort_id, "strategy": strategy, "min_score": min_score}
    ).fetchall()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["Rank", "Score", "Title", "Slug", "Watchers", "Average Rating"])
        for row in rows:
            writer.writerow(
                [
                    row.rank,
                    f"{row.score:.3f}",
                    row.title,
                    row.slug,
                    row.watchers or 0,
                    f"{row.avg_rating:.2f}" if row.avg_rating else "",
                ]
            )
    return len(rows)
