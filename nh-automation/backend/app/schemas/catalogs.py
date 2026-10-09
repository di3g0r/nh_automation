"""Request/response schemas for catalogs (FR-CAT)."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

PackagingCategory = Literal["envase", "caja", "bolsa", "etiqueta", "otro"]


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


# Products --------------------------------------------------------------------


class ProductOut(_Out):
    code: str
    name: str
    provider: str
    presentation: str
    container_liters: Decimal | None


class ProductCreate(_Stripped):
    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=200)
    provider: str = Field(min_length=1, max_length=200)
    presentation: str = Field(min_length=1, max_length=64)
    container_liters: Decimal | None = Field(default=None, gt=0, max_digits=12, decimal_places=2)


class ProductUpdate(_Stripped):
    code: str | None = Field(default=None, min_length=1, max_length=64)
    name: str | None = Field(default=None, min_length=1, max_length=200)
    provider: str | None = Field(default=None, min_length=1, max_length=200)
    presentation: str | None = Field(default=None, min_length=1, max_length=64)
    container_liters: Decimal | None = Field(default=None, gt=0, max_digits=12, decimal_places=2)
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
    has_api_key: bool
    last_seen_at: datetime | None

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
            last_seen_at=m.last_seen_at,
            created_at=m.created_at,
            updated_at=m.updated_at,
        )


class MachineWithKeyOut(BaseModel):
    """Returned only on creation and key rotation: the plain key, shown once."""

    machine: MachineOut
    api_key: str


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
