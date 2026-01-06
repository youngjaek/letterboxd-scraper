from __future__ import annotations

from sqlalchemy.orm import Session

from ..db import models
from ..scrapers.histograms import HistogramSummary


def upsert_global_histogram(
    session: Session,
    film: models.Film,
    summary: HistogramSummary,
) -> None:
    """
    Store the global Letterboxd histogram buckets for a film.

    Existing cohort-agnostic rows are replaced.
    """
    session.query(models.FilmHistogram).filter(
        models.FilmHistogram.film_id == film.id,
        models.FilmHistogram.cohort_id.is_(None),
    ).delete(synchronize_session=False)
    for bucket in summary.buckets:
        session.add(
            models.FilmHistogram(
                film_id=film.id,
                cohort_id=None,
                bucket_label=bucket.bucket_label,
                count=bucket.count,
            )
        )
    if summary.rating_count is not None:
        film.letterboxd_rating_count = summary.rating_count
    if summary.fan_count is not None:
        film.letterboxd_fan_count = summary.fan_count
    if summary.weighted_average is not None:
        film.letterboxd_weighted_average = summary.weighted_average


def film_needs_histogram(film: models.Film) -> bool:
    return film.letterboxd_rating_count is None
