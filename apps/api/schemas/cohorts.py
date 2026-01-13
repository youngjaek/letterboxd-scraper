from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


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
