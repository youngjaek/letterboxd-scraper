from __future__ import annotations

import contextlib
import time
from datetime import datetime, timezone
from typing import Iterable, Iterator, Optional

from sqlalchemy import update

from sqlalchemy.orm import Session

from ..db import models


def record_scrape_run(
    session: Session,
    *,
    cohort_id: Optional[int],
    run_type: str,
    status: str,
    notes: Optional[str] = None,
) -> int:
    run = models.ScrapeRun(
        cohort_id=cohort_id,
        run_type=run_type,
        status=status,
        notes=notes,
        started_at=datetime.now(timezone.utc),
    )
    session.add(run)
    session.flush()
    return run.id


def enqueue_scrape_members(
    session: Session,
    *,
    run_id: int,
    members: Iterable[tuple[str, str]],
) -> None:
    """Insert queued member rows for a scrape run."""
    for username, mode in members:
        session.add(
            models.ScrapeRunMember(
                run_id=run_id,
                username=username,
                status="queued",
                mode=mode,
            )
        )


def mark_member_started(session: Session, *, run_id: int, username: str) -> None:
    """Mark a member scrape as in progress."""
    session.execute(
        update(models.ScrapeRunMember)
        .where(
            models.ScrapeRunMember.run_id == run_id,
            models.ScrapeRunMember.username == username,
        )
        .values(status="scraping", started_at=datetime.now(timezone.utc), error=None)
    )


def mark_member_finished(
    session: Session,
    *,
    run_id: int,
    username: str,
    error: Optional[str] = None,
) -> None:
    """Mark a member scrape as completed or failed."""
    status = "failed" if error else "done"
    session.execute(
        update(models.ScrapeRunMember)
        .where(
            models.ScrapeRunMember.run_id == run_id,
            models.ScrapeRunMember.username == username,
        )
        .values(
            status=status,
            finished_at=datetime.now(timezone.utc),
            error=error,
        )
    )


def finalize_scrape_run(
    session: Session,
    run_id: int,
    *,
    status: Optional[str] = None,
    notes: Optional[str] = None,
) -> None:
    run = session.get(models.ScrapeRun, run_id)
    if not run:
        return
    run.finished_at = datetime.now(timezone.utc)
    if status:
        run.status = status
    if notes:
        run.notes = notes


@contextlib.contextmanager
def timed_operation(label: str) -> Iterator[RunTiming]:
    start = time.perf_counter()
    try:
        yield
    finally:
        duration = time.perf_counter() - start
        print(f"[telemetry] {label} completed in {duration:.2f}s")
