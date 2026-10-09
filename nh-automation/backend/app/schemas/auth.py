from __future__ import annotations

from pydantic import BaseModel, Field


class PasswordLogin(BaseModel):
    username: str
    password: str


class PinLogin(BaseModel):
    username: str
    pin: str = Field(min_length=4, max_length=6)


class ChangePassword(BaseModel):
    current_password: str
    new_password: str | None = Field(default=None, min_length=8, max_length=128)
    new_pin: str | None = Field(default=None, min_length=4, max_length=6)


class MeOut(BaseModel):
    id: int
    username: str
    full_name: str
    role: str
    permissions: list[str]
