"""Inventory schemas (FR-INV)."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, field_validator

ItemType = Literal["product", "packaging"]


class InventoryRow(BaseModel):
    item_type: ItemType
    item_id: int
    code: str
    name: str
    category: str | None  # packaging only
    is_active: bool
    site_id: int
    site_name: str
    on_hand: Decimal
    reserved: Decimal
    available: Decimal
    low_stock_threshold: int | None  # packaging only
    low_stock: bool
    negative: bool


class Availability(BaseModel):
    item_type: ItemType
    item_id: int
    site_id: int
    on_hand: Decimal
    reserved: Decimal
    available: Decimal


class _MovementIn(BaseModel):
    item_type: ItemType
    item_id: int
    site_id: int

    @field_validator("note", "reason", mode="before", check_fields=False)
    @classmethod
    def _strip(cls, v):  # type: ignore[no-untyped-def]
        return v.strip() if isinstance(v, str) else v


class ReceiptIn(_MovementIn):
    quantity: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    note: str | None = Field(default=None, max_length=1000)


class AdjustmentIn(_MovementIn):
    counted_quantity: Decimal = Field(ge=0, max_digits=12, decimal_places=2)
    reason: str = Field(min_length=1, max_length=1000)


class MovementOut(BaseModel):
    id: int
    created_at: datetime
    type: str
    item_type: ItemType
    item_id: int
    item_code: str
    item_name: str
    site_id: int
    site_name: str
    quantity: Decimal
    order_id: int | None
    assignment_id: int | None
    user_id: int | None
    user_name: str | None
    note: str | None


class AlertItem(BaseModel):
    kind: Literal["low_stock", "negative_stock"]
    item_type: ItemType
    item_id: int
    code: str
    name: str
    site_id: int
    site_name: str
    on_hand: Decimal
    available: Decimal
    low_stock_threshold: int | None


class AlertsOut(BaseModel):
    low_stock: list[AlertItem]
    negative_stock: list[AlertItem]
    count: int


class MovementUser(BaseModel):
    id: int
    full_name: str
