from __future__ import annotations

import contextlib
import time
from datetime import datetime, timezone
from typing import Iterator, Optional

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
