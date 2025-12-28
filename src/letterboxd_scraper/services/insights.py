from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from math import sqrt
from typing import Any, Dict, Iterable, List, Optional

from sqlalchemy import delete, text
from sqlalchemy.orm import Session

from ..db import models


@dataclass
class BucketFilters:
    release_start: Optional[int] = None
    release_end: Optional[int] = None
    watched_year: Optional[int] = None
    watched_since: Optional[datetime] = None
    watched_until: Optional[datetime] = None

    def to_timeframe_key(self) -> str:
        parts: list[str] = []
        if self.release_start or self.release_end:
            parts.append(f"release:{self.release_start or '-'}-{self.release_end or '-'}")
        if self.watched_year:
            parts.append(f"watched-year:{self.watched_year}")
        if self.watched_since or self.watched_until:
            since = self.watched_since.date().isoformat() if self.watched_since else "-"
            until = self.watched_until.date().isoformat() if self.watched_until else "-"
            parts.append(f"watched:{since}-{until}")
        return "|".join(parts) if parts else "all"

    def as_serializable_dict(self) -> Dict[str, Optional[str]]:
        return {
            "release_start": self.release_start,
            "release_end": self.release_end,
            "watched_year": self.watched_year,
            "watched_since": self.watched_since.isoformat() if self.watched_since else None,
            "watched_until": self.watched_until.isoformat() if self.watched_until else None,
        }

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> "BucketFilters":
        if not data:
            return cls()
        return cls(
            release_start=_coerce_int(data.get("release_start")),
            release_end=_coerce_int(data.get("release_end")),
            watched_year=_coerce_int(data.get("watched_year")),
            watched_since=_parse_datetime(data.get("watched_since")),
            watched_until=_parse_datetime(data.get("watched_until")),
        )


@dataclass
class FilmStat:
    film_id: int
    slug: str
    title: str
    release_year: Optional[int]
    watchers: int
    avg_rating: float
    first_rating_at: Optional[datetime]
    last_rating_at: Optional[datetime]


@dataclass
class FilmInsight:
    film_id: int
    slug: str
    title: str
    watchers: int
    avg_rating: float
    watchers_percentile: float
    rating_percentile: float
    watchers_zscore: float
    rating_zscore: float
    bucket_label: str
    cluster_label: str


@dataclass
class InsightComputation:
    cohort_id: int
    strategy: str
    timeframe_key: str
    filters: BucketFilters
    insights: List[FilmInsight]
    source: str = "computed"


STATS_SQL = text(
    """
    SELECT
        stats.film_id,
        stats.watchers,
        stats.avg_rating,
        stats.first_rating_at,
        stats.last_rating_at,
        f.slug,
        f.title,
        f.release_year
    FROM cohort_film_stats stats
    JOIN films f ON f.id = stats.film_id
    WHERE stats.cohort_id = :cohort_id
    """
)


def compute_ranking_buckets(
    session: Session, cohort_id: int, strategy: str, filters: Optional[BucketFilters] = None
) -> InsightComputation:
    applied_filters = filters or BucketFilters()
    rows = session.execute(STATS_SQL, {"cohort_id": cohort_id}).mappings().all()
    stats = [_row_to_stat(row) for row in rows]
    filtered_stats = [row for row in stats if _matches_filters(row, applied_filters)]
    insights = _derive_insights(filtered_stats)
    timeframe_key = applied_filters.to_timeframe_key()
    return InsightComputation(
        cohort_id=cohort_id,
        strategy=strategy,
        timeframe_key=timeframe_key,
        filters=applied_filters,
        insights=insights,
        source="computed",
    )


def persist_insights(session: Session, computation: InsightComputation) -> None:
    session.execute(
        delete(models.RankingInsight).where(
            models.RankingInsight.cohort_id == computation.cohort_id,
            models.RankingInsight.strategy == computation.strategy,
            models.RankingInsight.timeframe_key == computation.timeframe_key,
        )
    )
    for insight in computation.insights:
        session.add(
            models.RankingInsight(
                cohort_id=computation.cohort_id,
                strategy=computation.strategy,
                film_id=insight.film_id,
                timeframe_key=computation.timeframe_key,
                filters=computation.filters.as_serializable_dict(),
                watchers=insight.watchers,
                avg_rating=insight.avg_rating,
                watchers_percentile=insight.watchers_percentile,
                rating_percentile=insight.rating_percentile,
                watchers_zscore=insight.watchers_zscore,
                rating_zscore=insight.rating_zscore,
                bucket_label=insight.bucket_label,
                cluster_label=insight.cluster_label,
            )
        )


def load_saved_buckets(
    session: Session, cohort_id: int, strategy: str, timeframe_key: str
) -> Optional[InsightComputation]:
    rows = (
        session.query(
            models.RankingInsight,
            models.Film.slug,
            models.Film.title,
        )
        .join(models.Film, models.Film.id == models.RankingInsight.film_id)
        .filter(
            models.RankingInsight.cohort_id == cohort_id,
            models.RankingInsight.strategy == strategy,
            models.RankingInsight.timeframe_key == timeframe_key,
        )
        .order_by(
            models.RankingInsight.bucket_label.asc(),
            models.RankingInsight.rating_percentile.desc(),
            models.RankingInsight.watchers_percentile.desc(),
        )
        .all()
    )
    if not rows:
        return None
    sample_filters = BucketFilters.from_dict(rows[0].RankingInsight.filters)  # type: ignore[attr-defined]
    insights: List[FilmInsight] = []
    for row in rows:
        insight_row: models.RankingInsight = row.RankingInsight  # type: ignore[attr-defined]
        slug = row.slug  # type: ignore[attr-defined]
        title = row.title  # type: ignore[attr-defined]
        watchers = int(insight_row.watchers) if insight_row.watchers is not None else 0
        avg_rating = float(insight_row.avg_rating) if insight_row.avg_rating is not None else 0.0
        insights.append(
            FilmInsight(
                film_id=insight_row.film_id,
                slug=slug,
                title=title,
                watchers=watchers,
                avg_rating=avg_rating,
                watchers_percentile=float(insight_row.watchers_percentile or 0.0),
                rating_percentile=float(insight_row.rating_percentile or 0.0),
                watchers_zscore=float(insight_row.watchers_zscore or 0.0),
                rating_zscore=float(insight_row.rating_zscore or 0.0),
                bucket_label=insight_row.bucket_label or "Unlabeled",
                cluster_label=insight_row.cluster_label or "Unclustered",
            )
        )
    return InsightComputation(
        cohort_id=cohort_id,
        strategy=strategy,
        timeframe_key=timeframe_key,
        filters=sample_filters,
        insights=insights,
        source="stored",
    )


def _row_to_stat(row: Dict[str, Any]) -> FilmStat:
    watchers = int(row["watchers"] or 0)
    avg_rating_raw = row["avg_rating"]
    avg_rating = float(avg_rating_raw) if avg_rating_raw is not None else 0.0
    release_year_raw = row["release_year"]
    release_year = int(release_year_raw) if release_year_raw is not None else None
    return FilmStat(
        film_id=int(row["film_id"]),
        slug=row["slug"],
        title=row["title"],
        release_year=release_year,
        watchers=watchers,
        avg_rating=avg_rating,
        first_rating_at=row["first_rating_at"],
        last_rating_at=row["last_rating_at"],
    )


def _matches_filters(stat: FilmStat, filters: BucketFilters) -> bool:
    if filters.release_start and (stat.release_year or 0) < filters.release_start:
        return False
    if filters.release_end and stat.release_year and stat.release_year > filters.release_end:
        return False
    if filters.watched_year:
        if not stat.last_rating_at or stat.last_rating_at.year != filters.watched_year:
            return False
    if filters.watched_since:
        if not stat.last_rating_at or stat.last_rating_at < filters.watched_since:
            return False
    if filters.watched_until:
        if not stat.last_rating_at or stat.last_rating_at > filters.watched_until:
            return False
    return True


def _derive_insights(stats: Iterable[FilmStat]) -> List[FilmInsight]:
    rows = [stat for stat in stats if stat.watchers > 0 and stat.avg_rating > 0]
    if not rows:
        return []
    watcher_values = [stat.watchers for stat in rows]
    rating_values = [stat.avg_rating for stat in rows]
    watcher_percentiles = _percentile_lookup(watcher_values)
    rating_percentiles = _percentile_lookup(rating_values)
    watcher_mean = sum(watcher_values) / len(watcher_values)
    rating_mean = sum(rating_values) / len(rating_values)
    watcher_std = sqrt(sum((value - watcher_mean) ** 2 for value in watcher_values) / len(watcher_values))
    rating_std = sqrt(sum((value - rating_mean) ** 2 for value in rating_values) / len(rating_values))

    insights: List[FilmInsight] = []
    for stat in rows:
        w_pct = watcher_percentiles.get(stat.watchers, 0.0)
        r_pct = rating_percentiles.get(stat.avg_rating, 0.0)
        w_z = _zscore(stat.watchers, watcher_mean, watcher_std)
        r_z = _zscore(stat.avg_rating, rating_mean, rating_std)
        bucket = _bucket_label(w_pct, r_pct)
        cluster = _cluster_label(w_z, r_z)
        insights.append(
            FilmInsight(
                film_id=stat.film_id,
                slug=stat.slug,
                title=stat.title,
                watchers=stat.watchers,
                avg_rating=stat.avg_rating,
                watchers_percentile=w_pct,
                rating_percentile=r_pct,
                watchers_zscore=w_z,
                rating_zscore=r_z,
                bucket_label=bucket,
                cluster_label=cluster,
            )
        )
    insights.sort(key=lambda insight: (insight.bucket_label, -insight.rating_percentile, -insight.watchers_percentile))
    return insights


def _percentile_lookup(values: List[float]) -> Dict[float, float]:
    if not values:
        return {}
    sorted_vals = sorted(values)
    n = len(sorted_vals)
    first_seen: Dict[float, int] = {}
    last_seen: Dict[float, int] = {}
    for idx, value in enumerate(sorted_vals, start=1):
        first_seen.setdefault(value, idx)
        last_seen[value] = idx
    lookup: Dict[float, float] = {}
    for value, start_idx in first_seen.items():
        end_idx = last_seen[value]
        avg_rank = (start_idx + end_idx) / 2
        lookup[value] = (avg_rank / n) * 100.0
    return lookup


def _zscore(value: float, mean: float, std_dev: float) -> float:
    if std_dev == 0:
        return 0.0
    return (value - mean) / std_dev


def _bucket_label(watchers_pct: float, rating_pct: float) -> str:
    if watchers_pct >= 90 and rating_pct >= 90:
        return "Elite acclaim"
    if rating_pct >= 90 and watchers_pct < 50:
        return "Cult favorite"
    if watchers_pct >= 90 and 40 <= rating_pct <= 65:
        return "Crowd pleaser"
    if rating_pct >= 80 and watchers_pct >= 60:
        return "Critical favorite"
    if rating_pct >= 70 and watchers_pct < 30:
        return "Hidden gem"
    if watchers_pct >= 85 and rating_pct < 40:
        return "Guilty pleasure"
    if rating_pct < 30 and watchers_pct < 30:
        return "Skip it"
    return "Steady performer"


def _cluster_label(watchers_z: float, rating_z: float) -> str:
    if rating_z >= 1.0 and watchers_z >= 1.0:
        return "High rating / high watchers"
    if rating_z >= 1.0 and watchers_z <= -0.25:
        return "High rating / low watchers"
    if rating_z <= -1.0 and watchers_z >= 0.5:
        return "Low rating / high watchers"
    if rating_z <= -1.0 and watchers_z <= -0.25:
        return "Low rating / low watchers"
    if abs(rating_z) <= 0.5 and watchers_z >= 0.75:
        return "High engagement / mixed sentiment"
    if rating_z >= 0.5 and abs(watchers_z) <= 0.5:
        return "Critical darling"
    if rating_z <= -0.5 and abs(watchers_z) <= 0.5:
        return "Divisive pick"
    return "Middle of the pack"


def _coerce_int(value: Any) -> Optional[int]:
    if value is None or value == "":
        return None
    if isinstance(value, int):
        return value
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _parse_datetime(value: Any) -> Optional[datetime]:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None
