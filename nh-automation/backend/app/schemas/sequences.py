"""Order sequence schemas (phase 1b, BR-19)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class OrderSequenceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    order_type: str
    prefix: str
    next_number: int
    updated_at: datetime


class OrderSequenceUpdate(BaseModel):
    next_number: int = Field(ge=1)
