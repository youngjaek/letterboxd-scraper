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


class CohortDetail(CohortSummary):
    definition: CohortDefinition | None = None
    members: list[str]
