from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.permissions import Role

_VALID_ROLES = {r.value for r in Role}


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    full_name: str
    role: str
    is_active: bool
    has_pin: bool = False
    failed_attempts: int
    locked_until: datetime | None
    last_login_at: datetime | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_model(cls, user) -> UserOut:  # type: ignore[no-untyped-def]
        return cls(
            id=user.id,
            username=user.username,
            full_name=user.full_name,
            role=user.role,
            is_active=user.is_active,
            has_pin=bool(user.pin_hash),
            failed_attempts=user.failed_attempts,
            locked_until=user.locked_until,
            last_login_at=user.last_login_at,
            created_at=user.created_at,
            updated_at=user.updated_at,
        )


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    full_name: str = Field(min_length=1, max_length=200)
    role: str
    password: str = Field(min_length=8, max_length=128)
    pin: str | None = Field(default=None, min_length=4, max_length=6)

    @field_validator("role")
    @classmethod
    def role_must_be_known(cls, v: str) -> str:
        if v not in _VALID_ROLES:
            raise ValueError(f"Rol inválido: {v}")
        return v

    @field_validator("pin")
    @classmethod
    def pin_must_be_digits(cls, v: str | None) -> str | None:
        if v is not None and not v.isdigit():
            raise ValueError("El PIN debe contener solo dígitos.")
        return v


class UserUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=200)
    role: str | None = None

    @field_validator("role")
    @classmethod
    def role_must_be_known(cls, v: str | None) -> str | None:
        if v is not None and v not in _VALID_ROLES:
            raise ValueError(f"Rol inválido: {v}")
        return v


class ResetCredentials(BaseModel):
    password: str | None = Field(default=None, min_length=8, max_length=128)
    pin: str | None = Field(default=None, min_length=4, max_length=6)

    @field_validator("pin")
    @classmethod
    def pin_must_be_digits(cls, v: str | None) -> str | None:
        if v is not None and not v.isdigit():
            raise ValueError("El PIN debe contener solo dígitos.")
        return v
