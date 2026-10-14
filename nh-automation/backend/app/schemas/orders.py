"""Work order schemas (phase 2, FR-ORD / FR-INV-5..9)."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

OrderType = Literal["trabajo", "retrabajo"]
ReworkKind = Literal["previous_order", "own_stock"]
BarcodeMode = Literal["per_container", "per_box"]
OrderStatus = Literal[
    "created", "assigned", "in_progress", "paused", "completed", "closed", "cancelled"
]


def _strip(v: Any) -> Any:
    return v.strip() if isinstance(v, str) else v


class BaseProductIn(BaseModel):
    product_id: int
    liters: Decimal = Field(gt=0, max_digits=12, decimal_places=2)


class PackagingIn(BaseModel):
    packaging_item_id: int
    planned_qty: int = Field(gt=0)


class _OrderFields(BaseModel):
    model_config = ConfigDict(extra="forbid")

    @field_validator("comment", "previous_lot", mode="before", check_fields=False)
    @classmethod
    def _strip_text(cls, v):  # type: ignore[no-untyped-def]
        v = _strip(v)
        return v or None


class OrderCreate(_OrderFields):
    order_type: OrderType
    rework_kind: ReworkKind | None = None
    related_order_id: int | None = None
    client_id: int | None = None
    site_id: int | None = None  # default site when omitted
    order_date: date | None = None  # local today when omitted
    base_products: list[BaseProductIn] = Field(min_length=1)
    finished_product_id: int
    finished_liters: Decimal | None = Field(
        default=None, gt=0, max_digits=12, decimal_places=2
    )  # defaults to the sum of base product liters
    razon_social_id: int | None = None  # required only when base products mix (BR-22)
    comment: str | None = Field(default=None, max_length=2000)
    packaging: list[PackagingIn] = Field(default_factory=list)
    labels_planned: int | None = Field(default=None, ge=0)
    barcode_mode: BarcodeMode = "per_container"
    previous_lot: str | None = Field(default=None, max_length=100)


class OrderUpdate(_OrderFields):
    """PATCH: only sent fields change. `order_type` and `razon_social_id` are
    accepted only to reject a change with a clear error (BR-16, BR-21)."""

    order_type: OrderType | None = None
    razon_social_id: int | None = None
    rework_kind: ReworkKind | None = None
    related_order_id: int | None = None
    client_id: int | None = None
    site_id: int | None = None
    order_date: date | None = None
    base_products: list[BaseProductIn] | None = Field(default=None, min_length=1)
    finished_product_id: int | None = None
    finished_liters: Decimal | None = Field(
        default=None, gt=0, max_digits=12, decimal_places=2
    )
    comment: str | None = Field(default=None, max_length=2000)  # appended as a new comment
    packaging: list[PackagingIn] | None = None
    labels_planned: int | None = Field(default=None, ge=0)
    barcode_mode: BarcodeMode | None = None
    previous_lot: str | None = Field(default=None, max_length=100)


class CancelIn(BaseModel):
    reason: str = Field(min_length=1, max_length=2000)

    @field_validator("reason", mode="before")
    @classmethod
    def _strip_reason(cls, v):  # type: ignore[no-untyped-def]
        return _strip(v)


class CommentIn(BaseModel):
    text: str = Field(min_length=1, max_length=2000)

    @field_validator("text", mode="before")
    @classmethod
    def _strip_text(cls, v):  # type: ignore[no-untyped-def]
        return _strip(v)


# Output ------------------------------------------------------------------------


class BaseProductOut(BaseModel):
    position: int
    product_id: int
    code: str
    name: str
    provider: str
    presentation: str
    razon_social_code: str
    liters: Decimal


class PackagingOut(BaseModel):
    packaging_item_id: int
    code: str
    description: str
    planned_qty: int
    actual_qty: int | None
    actual_by_name: str | None
    actual_at: datetime | None


class ChecklistOut(BaseModel):
    item: str
    checked: bool
    checked_by_name: str | None
    checked_at: datetime | None


class CommentOut(BaseModel):
    id: int
    user_id: int
    user_name: str
    text: str
    created_at: datetime


class OrderOut(BaseModel):
    id: int
    order_type: OrderType
    sequence: int
    operation_number: str
    rework_kind: ReworkKind | None
    related_order_id: int | None
    related_operation_number: str | None
    client_id: int | None
    client_name: str | None
    razon_social_id: int
    razon_social_code: str
    razon_social_name: str
    site_id: int
    site_name: str
    order_date: date
    base_products: list[BaseProductOut]
    base_liters_total: Decimal
    finished_product_id: int
    finished_code: str
    finished_name: str
    finished_provider: str
    finished_presentation: str
    finished_liters: Decimal
    packaging: list[PackagingOut]
    checklist: list[ChecklistOut]
    labels_planned: int | None
    labels_actual: int | None
    barcode_mode: BarcodeMode
    previous_lot: str | None
    new_lot: str | None
    expiry_date: date | None
    expiry_locked: bool
    status: OrderStatus
    warnings: list[dict[str, Any]]
    created_by: int
    created_by_name: str
    created_at: datetime
    updated_at: datetime
    cancelled_by_name: str | None
    cancelled_at: datetime | None
    cancel_reason: str | None
    closed_by_name: str | None
    closed_at: datetime | None
    close_note: str | None
    # Status-based flags; the UI combines them with the user's permissions.
    can_edit: bool
    can_cancel: bool
    can_delete: bool


class OrderListItem(BaseModel):
    id: int
    order_type: OrderType
    operation_number: str
    rework_kind: ReworkKind | None
    status: OrderStatus
    order_date: date
    client_name: str | None
    razon_social_code: str
    site_name: str
    base_products: list[str]  # "CODE — NAME"
    finished_code: str
    finished_name: str
    finished_liters: Decimal
    has_warnings: bool
    created_at: datetime


class HistoryEntry(BaseModel):
    id: int
    created_at: datetime
    user_id: int | None
    user_name: str | None
    action: str
    before: dict[str, Any] | None
    after: dict[str, Any] | None


class Signature(BaseModel):
    name: str
    at: datetime


class PrintData(BaseModel):
    order: OrderOut
    comments: list[CommentOut]  # oldest first, as on paper
    created: Signature
    assigned: Signature | None  # phase 3
    closed: Signature | None
    barcodes: dict[str, str]  # TODO(OPEN-12): label/barcode printing integration


class ReservationHolder(BaseModel):
    order_id: int
    operation_number: str
    order_type: OrderType
    status: OrderStatus
    quantity: Decimal
    created_at: datetime
