"""Stock tables (data model §2, phase 1): stock_levels and stock_movements.

Each row refers to exactly one item: a product (liters) xor a packaging item
(units). `on_hand` only changes together with a movement (BR-5); see
app/services/stock_service.py.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin

MOVEMENT_TYPES = ("receipt", "adjustment", "consumption", "production")

_ITEM_XOR = (
    "(product_id IS NOT NULL AND packaging_item_id IS NULL) OR "
    "(product_id IS NULL AND packaging_item_id IS NOT NULL)"
)


class StockLevel(Base, TimestampMixin):
    __tablename__ = "stock_levels"
    __table_args__ = (
        CheckConstraint(_ITEM_XOR, name="ck_stock_levels_item_xor"),
        UniqueConstraint("site_id", "product_id", name="uq_stock_levels_site_product"),
        UniqueConstraint("site_id", "packaging_item_id", name="uq_stock_levels_site_packaging"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    site_id: Mapped[int] = mapped_column(ForeignKey("sites.id"), nullable=False, index=True)
    product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id"), nullable=True)
    packaging_item_id: Mapped[int | None] = mapped_column(
        ForeignKey("packaging_items.id"), nullable=True
    )
    # NUMERIC for both item kinds; packaging quantities are validated as whole
    # units in the service layer (see docs/DECISIONS.md, phase 1).
    on_hand: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("0"))


class StockMovement(Base, TimestampMixin):
    __tablename__ = "stock_movements"
    __table_args__ = (
        CheckConstraint(_ITEM_XOR, name="ck_stock_movements_item_xor"),
        Index("ix_stock_movements_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    site_id: Mapped[int] = mapped_column(ForeignKey("sites.id"), nullable=False, index=True)
    product_id: Mapped[int | None] = mapped_column(
        ForeignKey("products.id"), nullable=True, index=True
    )
    packaging_item_id: Mapped[int | None] = mapped_column(
        ForeignKey("packaging_items.id"), nullable=True, index=True
    )
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)  # signed
    # work_orders / assignments tables arrive in phases 2 and 3; those phases
    # add the foreign keys. Plain integers until then.
    order_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    assignment_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
