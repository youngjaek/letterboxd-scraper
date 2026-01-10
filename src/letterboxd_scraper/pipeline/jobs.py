from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Dict, Iterator, Optional

from ..config import Settings
from ..db import models
from ..db.session import get_session


@contextmanager
def job_run(
    settings: Settings,
    job_name: str,
    *,
    cohort_id: Optional[int] = None,
    user_id: Optional[int] = None,
    payload: Optional[Dict[str, Any]] = None,
) -> Iterator[int]:
    run_id = _create_job_run(settings, job_name, cohort_id=cohort_id, user_id=user_id, payload=payload)
    try:
        yield run_id
    except Exception as exc:
        _finalize_job_run(settings, run_id, status="failed", error=str(exc))
        raise
    else:
        _finalize_job_run(settings, run_id, status="succeeded", error=None)


def _create_job_run(
    settings: Settings,
    job_name: str,
    *,
    cohort_id: Optional[int],
    user_id: Optional[int],
    payload: Optional[Dict[str, Any]],
) -> int:
    with get_session(settings) as session:
        run = models.JobRun(
            job_name=job_name,
            cohort_id=cohort_id,
            user_id=user_id,
            status="running",
            payload=payload,
            started_at=datetime.now(timezone.utc),
        )
        session.add(run)
        session.flush()
        return int(run.id)


def _finalize_job_run(
    settings: Settings,
    run_id: int,
    *,
    status: str,
    error: Optional[str],
) -> None:
    with get_session(settings) as session:
        run = session.get(models.JobRun, run_id)
        if not run:
            return
        run.status = status
        run.finished_at = datetime.now(timezone.utc)
        run.last_error = error
