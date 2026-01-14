from __future__ import annotations

from datetime import datetime

from typing import Any, Dict

from pydantic import BaseModel, ConfigDict


class CohortSummary(BaseModel):
    id: int
    label: str
    seed_user_id: int | None = None
    member_count: int
    created_at: datetime
    updated_at: datetime | None = None
    current_task_id: str | None = None

    model_config = {
        "from_attributes": True,
    }


class CohortDefinition(BaseModel):
    depth: int | None = None
    include_seed: bool | None = None
    min_votes: int | None = None
    m_value: int | None = None
    filters: Dict[str, Any] | None = None

    model_config = ConfigDict(extra="allow")


class CohortMemberProfile(BaseModel):
    username: str
    avatar_url: str | None = None


class CohortDetail(CohortSummary):
    definition: CohortDefinition | None = None
    members: list[CohortMemberProfile]
    seed_username: str | None = None


class ScrapeMemberStatus(BaseModel):
    username: str
    status: str
    mode: str
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error: str | None = None


class ScrapeProgress(BaseModel):
    status: str
    run_id: int | None = None
    run_type: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    total_members: int = 0
    completed: int = 0
    failed: int = 0
    queued: int = 0
    in_progress: list[ScrapeMemberStatus] = []
    recent_finished: list[ScrapeMemberStatus] = []


class CohortCreateRequest(BaseModel):
    seed_username: str
    label: str
    depth: int | None = None
    include_seed: bool | None = None
