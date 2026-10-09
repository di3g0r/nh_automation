from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class SettingOut(BaseModel):
    key: str
    value: Any


class SettingUpdate(BaseModel):
    value: Any
