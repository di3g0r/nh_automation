"""Request/response schemas for catalogs (FR-CAT)."""

from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

PackagingCategory = Literal["envase", "caja", "bolsa", "etiqueta", "otro"]

RAZON_SOCIAL_CODE = re.compile(r"^[A-Z0-9]{1,6}$")


def normalize_razon_social_code(v: str) -> str:
    """Uppercase, then require 1-6 letters/digits (it becomes the order-number suffix)."""
    code = v.strip().upper()
    if not RAZON_SOCIAL_CODE.match(code):
        raise ValueError("El código debe tener de 1 a 6 letras mayúsculas o dígitos, sin espacios.")
    return code


def _strip(v: str | None) -> str | None:
    return v.strip() if isinstance(v, str) else v


class _Stripped(BaseModel):
    """Strip surrounding whitespace from every string field."""

    @field_validator("*", mode="before")
    @classmethod
    def _strip_strings(cls, v):  # type: ignore[no-untyped-def]
        return _strip(v)


class _Out(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    is_active: bool
    created_at: datetime
    updated_at: datetime


# Sites -----------------------------------------------------------------------


class SiteOut(_Out):
    name: str
    is_default: bool


class SiteCreate(_Stripped):
    name: str = Field(min_length=1, max_length=200)
    is_default: bool = False


class SiteUpdate(_Stripped):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    is_default: bool | None = None
    is_active: bool | None = None


# Clients ---------------------------------------------------------------------


class ClientOut(_Out):
    name: str
    code: str


class ClientCreate(_Stripped):
    name: str = Field(min_length=1, max_length=200)
    code: str = Field(min_length=1, max_length=32)


class ClientUpdate(_Stripped):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    code: str | None = Field(default=None, min_length=1, max_length=32)
    is_active: bool | None = None


# Razones sociales --------------------------------------------------------------


class RazonSocialOut(_Out):
    code: str
    name: str


class RazonSocialCreate(_Stripped):
    code: str = Field(min_length=1, max_length=6)
    name: str = Field(min_length=1, max_length=200)

    @field_validator("code")
    @classmethod
    def _code(cls, v: str) -> str:
        return normalize_razon_social_code(v)


class RazonSocialUpdate(_Stripped):
    # Phase 2 will block changing a code already used by an order.
    code: str | None = Field(default=None, min_length=1, max_length=6)
    name: str | None = Field(default=None, min_length=1, max_length=200)
    is_active: bool | None = None

    @field_validator("code")
    @classmethod
    def _code(cls, v: str | None) -> str | None:
        return normalize_razon_social_code(v) if v is not None else None


# Products --------------------------------------------------------------------


class ProductOut(_Out):
    code: str
    name: str
    provider: str
    presentation: str
    container_liters: Decimal | None
    razon_social_id: int | None
    razon_social_code: str | None
    razon_social_name: str | None

    @classmethod
    def from_model(cls, p) -> ProductOut:  # type: ignore[no-untyped-def]
        rs = p.razon_social
        return cls(
            id=p.id,
            code=p.code,
            name=p.name,
            provider=p.provider,
            presentation=p.presentation,
            container_liters=p.container_liters,
            razon_social_id=p.razon_social_id,
            razon_social_code=rs.code if rs else None,
            razon_social_name=rs.name if rs else None,
            is_active=p.is_active,
            created_at=p.created_at,
            updated_at=p.updated_at,
        )


class ProductCreate(_Stripped):
    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=200)
    provider: str = Field(min_length=1, max_length=200)
    presentation: str = Field(min_length=1, max_length=64)
    container_liters: Decimal | None = Field(default=None, gt=0, max_digits=12, decimal_places=2)
    razon_social_id: int


class ProductUpdate(_Stripped):
    code: str | None = Field(default=None, min_length=1, max_length=64)
    name: str | None = Field(default=None, min_length=1, max_length=200)
    provider: str | None = Field(default=None, min_length=1, max_length=200)
    presentation: str | None = Field(default=None, min_length=1, max_length=64)
    container_liters: Decimal | None = Field(default=None, gt=0, max_digits=12, decimal_places=2)
    # Omit to keep the current value; an explicit null is rejected (required).
    razon_social_id: int | None = None
    is_active: bool | None = None


# Packaging items -------------------------------------------------------------


class PackagingItemOut(_Out):
    code: str
    description: str
    category: str
    low_stock_threshold: int


class PackagingItemCreate(_Stripped):
    code: str = Field(min_length=1, max_length=64)
    description: str = Field(min_length=1, max_length=200)
    category: PackagingCategory
    low_stock_threshold: int = Field(default=0, ge=0)


class PackagingItemUpdate(_Stripped):
    code: str | None = Field(default=None, min_length=1, max_length=64)
    description: str | None = Field(default=None, min_length=1, max_length=200)
    category: PackagingCategory | None = None
    low_stock_threshold: int | None = Field(default=None, ge=0)
    is_active: bool | None = None


# Machines --------------------------------------------------------------------


class MachineOut(_Out):
    code: str
    name: str
    site_id: int
    site_name: str
    in_maintenance: bool
    has_api_key: bool  # phase-1 artifact, hidden in the UI since phase 4
    plc_db_username: str | None  # phase 4: the PLC's PostgreSQL login
    last_seen_at: datetime | None  # last PLC contact (plc_events trigger)

    @classmethod
    def from_model(cls, m) -> MachineOut:  # type: ignore[no-untyped-def]
        return cls(
            id=m.id,
            code=m.code,
            name=m.name,
            site_id=m.site_id,
            site_name=m.site.name,
            is_active=m.is_active,
            in_maintenance=m.in_maintenance,
            has_api_key=bool(m.api_key_hash),
            plc_db_username=m.plc_db_username,
            last_seen_at=m.last_seen_at,
            created_at=m.created_at,
            updated_at=m.updated_at,
        )


class MachineWithKeyOut(BaseModel):
    """Returned only on creation and key rotation: the plain key, shown once."""

    machine: MachineOut
    api_key: str


class PlcCredentialsOut(BaseModel):
    """Returned only when a PLC login is created or rotated: the password is
    shown once and never stored by the app (phase 4)."""

    machine: MachineOut
    username: str
    password: str
    created: bool  # False = new password for an existing login
    host: str  # PLC_DB_HOST ("" if not configured)
    port: int
    database: str


class MachineCreate(_Stripped):
    code: str = Field(min_length=1, max_length=32)
    name: str = Field(min_length=1, max_length=200)
    site_id: int
    in_maintenance: bool = False


class MachineUpdate(_Stripped):
    code: str | None = Field(default=None, min_length=1, max_length=32)
    name: str | None = Field(default=None, min_length=1, max_length=200)
    site_id: int | None = None
    in_maintenance: bool | None = None
    is_active: bool | None = None
