from __future__ import annotations

import os
from dataclasses import asdict
from functools import lru_cache
from pathlib import Path
from typing import Iterator, List, Optional, Sequence

from celery import Celery
from celery.schedules import crontab
from sqlalchemy import select

from ..config import Settings, load_settings
from ..db import models
from ..db.session import get_session
from ..services import workflows as workflow_service
from .jobs import job_run


@lru_cache(maxsize=1)
def _load_settings() -> Settings:
    config_path = os.getenv("LETTERBOXD_CONFIG")
    path = Path(config_path) if config_path else None
    return load_settings(config_path=path)


celery_app = Celery("letterboxd_scraper")
settings = _load_settings()
celery_app.conf.update(
    broker_url=settings.task_queue.broker_url,
    result_backend=settings.task_queue.result_backend,
    task_default_queue=settings.task_queue.default_queue,
    task_routes={
        "letterboxd.tasks.scrape_user_batch": {"queue": settings.task_queue.scrape_queue},
        "letterboxd.tasks.schedule_incremental_user_scrapes": {"queue": settings.task_queue.scrape_queue},
        "letterboxd.tasks.run_cohort_pipeline": {"queue": settings.task_queue.stats_queue},
        "letterboxd.tasks.refresh_stats": {"queue": settings.task_queue.stats_queue},
        "letterboxd.tasks.compute_rankings": {"queue": settings.task_queue.stats_queue},
        "letterboxd.tasks.enrich_missing_films": {"queue": settings.task_queue.enrichment_queue},
        "letterboxd.tasks.schedule_full_enrichment": {"queue": settings.task_queue.enrichment_queue},
    },
)
celery_app.conf.beat_schedule = {
    "daily-incremental-scrapes": {
        "task": "letterboxd.tasks.schedule_incremental_user_scrapes",
        "schedule": crontab(hour=4, minute=0),
        "args": (),
    },
    "weekly-full-enrichment": {
        "task": "letterboxd.tasks.schedule_full_enrichment",
        "schedule": crontab(hour=3, minute=0, day_of_week="sun"),
        "args": (),
    },
}


@celery_app.task(name="letterboxd.tasks.run_cohort_pipeline")
def run_cohort_pipeline(cohort_id: int, incremental: bool = True) -> dict:
    """Orchestrate refresh → scrape → stats → rankings → enrichment for a cohort."""
    settings = _load_settings()
    with job_run(
        settings,
        "cohort_pipeline",
        cohort_id=cohort_id,
        payload={"incremental": incremental},
    ):
        refresh_result = workflow_service.refresh_cohort_membership(settings, cohort_id)
        scrape_summary = workflow_service.scrape_cohort_members(
            settings, cohort_id, incremental=incremental
        )
        stats_result = workflow_service.refresh_stats(settings, concurrently=False)
        ranking_result = workflow_service.compute_rankings(settings, cohort_id)
        bucket_result = workflow_service.compute_bucket_insights(settings, cohort_id)
        film_ids = list(scrape_summary.touched_film_ids)
        enrichment_result = workflow_service.enrich_films(
            settings,
            film_ids=film_ids or None,
            limit=len(film_ids) if film_ids else 50,
        )
    return {
        "refresh": {
            "cohort_id": refresh_result.cohort_id,
            "depth": refresh_result.depth,
            "include_seed": refresh_result.include_seed,
            "edges_discovered": refresh_result.edges_discovered,
            "member_count": refresh_result.member_count,
        },
        "scrape": {
            "cohort_id": scrape_summary.cohort_id,
            "requested_members": scrape_summary.requested_members,
            "processed_members": scrape_summary.processed_members,
            "total_entries": scrape_summary.total_entries,
            "touched_film_ids": sorted(scrape_summary.touched_film_ids),
            "incremental": scrape_summary.incremental,
        },
        "stats": {"concurrent": stats_result.concurrently},
        "rankings": {
            "cohort_id": ranking_result.cohort_id,
            "strategy": ranking_result.strategy,
            "computed_rows": ranking_result.computed_rows,
        },
        "buckets": {
            "cohort_id": bucket_result.cohort_id,
            "strategy": bucket_result.strategy,
            "timeframe_key": bucket_result.timeframe_key,
            "rows": bucket_result.rows,
            "persisted": bucket_result.persisted,
        },
        "enrichment": asdict(enrichment_result),
    }


@celery_app.task(name="letterboxd.tasks.scrape_user_batch")
def scrape_user_batch(usernames: Sequence[str], incremental: bool = True) -> dict:
    """Scrape a batch of Letterboxd usernames."""
    settings = _load_settings()
    results = []
    with job_run(
        settings,
        "scrape_user_batch",
        payload={"usernames": list(usernames), "incremental": incremental},
    ):
        for username in usernames:
            result = workflow_service.scrape_user_ratings(
                settings,
                username,
                incremental=incremental,
                persist=True,
                include_entries=False,
            )
            results.append(
                {
                    "username": username,
                    "fetched": result.fetched,
                    "liked_only": result.liked_only,
                    "touched_film_ids": sorted(result.touched_film_ids),
                }
            )
    return {"processed": len(usernames), "results": results}


@celery_app.task(name="letterboxd.tasks.schedule_incremental_user_scrapes")
def schedule_incremental_user_scrapes(batch_size: int = 200) -> dict:
    """Split all known users into scrape batches for incremental refresh."""
    settings = _load_settings()
    with job_run(settings, "schedule_incremental_scrapes", payload={"batch_size": batch_size}):
        with get_session(settings) as session:
            stmt = (
                select(models.User.letterboxd_username)
                .order_by(models.User.last_incremental_scrape_at.asc().nullsfirst(), models.User.id.asc())
            )
            usernames = [row[0] for row in session.execute(stmt)]
        batches = list(_chunk(usernames, batch_size))
        for batch in batches:
            scrape_user_batch.apply_async(
                args=[batch, True],
                queue=settings.task_queue.scrape_queue,
            )
    return {"total_users": len(usernames), "batches": len(batches), "batch_size": batch_size}


@celery_app.task(name="letterboxd.tasks.enrich_missing_films")
def enrich_missing_films(film_ids: Optional[Sequence[int]] = None, limit: int = 50) -> dict:
    """Enrich metadata for provided films or the next batch needing data."""
    settings = _load_settings()
    payload = {"film_ids": list(film_ids) if film_ids else None, "limit": limit}
    with job_run(settings, "enrich_films", payload=payload):
        result = workflow_service.enrich_films(
            settings,
            film_ids=film_ids,
            limit=limit,
        )
    return asdict(result)


@celery_app.task(name="letterboxd.tasks.schedule_full_enrichment")
def schedule_full_enrichment(batch_size: int = 25) -> dict:
    """Kick off enrichment jobs covering every film in the catalog."""
    settings = _load_settings()
    with job_run(settings, "schedule_full_enrichment", payload={"batch_size": batch_size}):
        with get_session(settings) as session:
            stmt = select(models.Film.id).order_by(models.Film.id.asc())
            film_ids = [row[0] for row in session.execute(stmt)]
        batches = list(_chunk(film_ids, batch_size))
        for batch in batches:
            enrich_missing_films.apply_async(
                args=[batch, len(batch)],
                queue=settings.task_queue.enrichment_queue,
            )
    return {"total_films": len(film_ids), "batches": len(batches), "batch_size": batch_size}


def _chunk(items: Sequence[str | int], size: int) -> Iterator[List[str | int]]:
    size = max(1, size)
    current: List[str | int] = []
    for item in items:
        current.append(item)
        if len(current) >= size:
            yield current
            current = []
    if current:
        yield current
