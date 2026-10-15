"""Work order tables (data model §2 / §2.1, phase 2).

An order has one or more base products (*Producto base*) and one finished
product (*Producto terminado*). Product data is snapshotted on save
(FR-ORD-1) so later catalog edits never change an existing order.
Reservations hold stock for the order until it is consumed, cancelled or
deleted (BR-1, BR-10).
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin
from app.db.types import JSONVariant

ORDER_STATUSES = (
    "created", "assigned", "in_progress", "paused", "completed", "closed", "cancelled"
)
REWORK_KINDS = ("previous_order", "own_stock")
BARCODE_MODES = ("per_container", "per_box")
CHECKLIST_ITEMS = ("lote_etiqueta", "niveles_producto", "cantidades", "embalaje")
RESERVATION_STATUSES = ("active", "consumed", "released")


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN (" + ", ".join(f"'{v}'" for v in values) + ")"


class WorkOrder(Base, TimestampMixin):
    __tablename__ = "work_orders"
    __table_args__ = (
        CheckConstraint(_in("order_type", ("trabajo", "retrabajo")), name="ck_work_orders_type"),
        CheckConstraint(_in("status", ORDER_STATUSES), name="ck_work_orders_status"),
        CheckConstraint(
            "rework_kind IS NULL OR " + _in("rework_kind", REWORK_KINDS),
            name="ck_work_orders_rework_kind",
        ),
        CheckConstraint(_in("barcode_mode", BARCODE_MODES), name="ck_work_orders_barcode_mode"),
        CheckConstraint("finished_liters > 0", name="ck_work_orders_finished_liters"),
        # BR-19: numbers are never reused, whatever the razón social suffix.
        UniqueConstraint("order_type", "sequence", name="uq_work_orders_type_sequence"),
        Index("ix_work_orders_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_type: Mapped[str] = mapped_column(String(16), nullable=False)  # immutable (BR-21)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    operation_number: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    rework_kind: Mapped[str | None] = mapped_column(String(16), nullable=True)
    related_order_id: Mapped[int | None] = mapped_column(
        ForeignKey("work_orders.id"), nullable=True
    )
    client_id: Mapped[int | None] = mapped_column(
        ForeignKey("clients.id"), nullable=True, index=True
    )
    razon_social_id: Mapped[int] = mapped_column(
        ForeignKey("razones_sociales.id"), nullable=False, index=True
    )
    site_id: Mapped[int] = mapped_column(ForeignKey("sites.id"), nullable=False, index=True)
    order_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)

    finished_product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id"), nullable=False, index=True
    )
    finished_code: Mapped[str] = mapped_column(String(64), nullable=False)
    finished_name: Mapped[str] = mapped_column(String(200), nullable=False)
    finished_provider: Mapped[str] = mapped_column(String(200), nullable=False)
    finished_presentation: Mapped[str] = mapped_column(String(64), nullable=False)
    finished_liters: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)

    barcode_mode: Mapped[str] = mapped_column(String(16), nullable=False)
    labels_planned: Mapped[int | None] = mapped_column(Integer, nullable=True)
    labels_actual: Mapped[int | None] = mapped_column(Integer, nullable=True)
    labels_actual_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    labels_actual_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # TODO(OPEN-4): lot format undecided; free text.
    previous_lot: Mapped[str | None] = mapped_column(String(100), nullable=True)
    new_lot: Mapped[str | None] = mapped_column(String(100), nullable=True)
    new_lot_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    new_lot_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # BR-20: null until set by the Production manager (phase 3), except
    # Retrabajo de orden anterior, which copies the related order's expiry.
    # TODO(OPEN-4): stored as the 1st of the month, shown MM/AAAA.
    expiry_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    expiry_set_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    expiry_set_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    status: Mapped[str] = mapped_column(String(16), nullable=False, default="created", index=True)
    warnings: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONVariant, nullable=False, default=list
    )

    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    closed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    close_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    cancelled_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancel_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    base_products: Mapped[list[OrderBaseProduct]] = relationship(
        back_populates="order",
        cascade="all, delete-orphan",
        order_by="OrderBaseProduct.position",
    )
    packaging: Mapped[list[OrderPackaging]] = relationship(
        back_populates="order", cascade="all, delete-orphan", order_by="OrderPackaging.id"
    )
    checklist: Mapped[list[OrderChecklistItem]] = relationship(
        cascade="all, delete-orphan", order_by="OrderChecklistItem.id"
    )
    comments: Mapped[list[OrderComment]] = relationship(
        cascade="all, delete-orphan", order_by="OrderComment.id"
    )
    reservations: Mapped[list[Reservation]] = relationship(cascade="all, delete-orphan")


class OrderBaseProduct(Base, TimestampMixin):
    __tablename__ = "order_base_products"
    __table_args__ = (
        UniqueConstraint("order_id", "product_id", name="uq_order_base_products_product"),
        CheckConstraint("liters > 0", name="ck_order_base_products_liters"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(
        ForeignKey("work_orders.id", ondelete="CASCADE"), nullable=False, index=True
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False, index=True)
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    provider: Mapped[str] = mapped_column(String(200), nullable=False)
    presentation: Mapped[str] = mapped_column(String(64), nullable=False)
    razon_social_code: Mapped[str] = mapped_column(String(6), nullable=False)
    liters: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)

    order: Mapped[WorkOrder] = relationship(back_populates="base_products")


class OrderPackaging(Base, TimestampMixin):
    __tablename__ = "order_packaging"
    __table_args__ = (
        UniqueConstraint("order_id", "packaging_item_id", name="uq_order_packaging_item"),
        CheckConstraint("planned_qty > 0", name="ck_order_packaging_planned"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(
        ForeignKey("work_orders.id", ondelete="CASCADE"), nullable=False, index=True
    )
    packaging_item_id: Mapped[int] = mapped_column(
        ForeignKey("packaging_items.id"), nullable=False
    )
    planned_qty: Mapped[int] = mapped_column(Integer, nullable=False)
    actual_qty: Mapped[int | None] = mapped_column(Integer, nullable=True)
    actual_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    actual_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    order: Mapped[WorkOrder] = relationship(back_populates="packaging")


class OrderChecklistItem(Base, TimestampMixin):
    __tablename__ = "order_checklist"
    __table_args__ = (
        UniqueConstraint("order_id", "item", name="uq_order_checklist_item"),
        CheckConstraint(_in("item", CHECKLIST_ITEMS), name="ck_order_checklist_item"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(
        ForeignKey("work_orders.id", ondelete="CASCADE"), nullable=False, index=True
    )
    item: Mapped[str] = mapped_column(String(32), nullable=False)
    checked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    checked_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class OrderComment(Base, TimestampMixin):
    """Append-only (data model §2): no update or delete endpoints."""

    __tablename__ = "order_comments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(
        ForeignKey("work_orders.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)


_ITEM_XOR = (
    "(product_id IS NOT NULL AND packaging_item_id IS NULL) OR "
    "(product_id IS NULL AND packaging_item_id IS NOT NULL)"
)


class Reservation(Base, TimestampMixin):
    __tablename__ = "reservations"
    __table_args__ = (
        CheckConstraint(_ITEM_XOR, name="ck_reservations_item_xor"),
        CheckConstraint(_in("status", RESERVATION_STATUSES), name="ck_reservations_status"),
        CheckConstraint("quantity > 0", name="ck_reservations_quantity"),
        Index("ix_reservations_site_product_status", "site_id", "product_id", "status"),
        Index("ix_reservations_site_packaging_status", "site_id", "packaging_item_id", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(
        ForeignKey("work_orders.id", ondelete="CASCADE"), nullable=False, index=True
    )
    site_id: Mapped[int] = mapped_column(ForeignKey("sites.id"), nullable=False)
    product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id"), nullable=True)
    packaging_item_id: Mapped[int | None] = mapped_column(
        ForeignKey("packaging_items.id"), nullable=True
    )
    quantity: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
