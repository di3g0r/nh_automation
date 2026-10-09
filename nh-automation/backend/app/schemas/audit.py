from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class AuditLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int | None
    entity: str
    entity_id: int | None
    action: str
    before: dict[str, Any] | None
    after: dict[str, Any] | None
    created_at: datetime
