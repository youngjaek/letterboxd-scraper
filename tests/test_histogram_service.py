from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from letterboxd_scraper.db import models
from letterboxd_scraper.scrapers.histograms import HistogramBucket, HistogramSummary
from letterboxd_scraper.services import histograms as histogram_service


def make_session() -> Session:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    models.Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    return SessionLocal()


def test_upsert_global_histogram_persists_buckets_and_stats():
    session = make_session()
    film = models.Film(slug="sample", title="Sample Film")
    session.add(film)
    session.commit()
    summary = HistogramSummary(
        slug="sample",
        weighted_average=4.25,
        rating_count=1000,
        fan_count=500,
        buckets=[
            HistogramBucket(bucket_label="4.5", rating_value=4.5, count=600, percentage=60.0),
            HistogramBucket(bucket_label="5", rating_value=5.0, count=400, percentage=40.0),
        ],
    )
    histogram_service.upsert_global_histogram(session, film, summary)
    session.commit()
    rows = session.execute(
        select(models.FilmHistogram).where(models.FilmHistogram.film_id == film.id)
    ).scalars().all()
    assert len(rows) == 2
    assert film.letterboxd_rating_count == 1000
    assert film.letterboxd_fan_count == 500
    assert float(film.letterboxd_weighted_average or 0) == 4.25
    session.close()


def test_film_needs_histogram():
    film = models.Film(slug="slug", title="Title")
    assert histogram_service.film_needs_histogram(film)
    film.letterboxd_rating_count = 10
    assert not histogram_service.film_needs_histogram(film)
