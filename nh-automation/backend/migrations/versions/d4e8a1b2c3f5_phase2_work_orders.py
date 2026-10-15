"""phase2 work orders: work_orders, order_base_products, order_packaging,
order_checklist, order_comments, reservations; FK stock_movements.order_id

Revision ID: d4e8a1b2c3f5
Revises: c7d2f4a8b913
Create Date: 2026-10-13

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "d4e8a1b2c3f5"
down_revision: Union[str, None] = "c7d2f4a8b913"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Frozen copies (migrations must not depend on app code that may change later).
_STATUSES = ("created", "assigned", "in_progress", "paused", "completed", "closed", "cancelled")
_CHECKLIST = ("lote_etiqueta", "niveles_producto", "cantidades", "embalaje")
_ITEM_XOR = (
    "(product_id IS NOT NULL AND packaging_item_id IS NULL) OR "
    "(product_id IS NULL AND packaging_item_id IS NOT NULL)"
)


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN (" + ", ".join(f"'{v}'" for v in values) + ")"


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    ]


def _user_fk(name: str) -> sa.Column:
    return sa.Column(name, sa.Integer(), sa.ForeignKey("users.id"), nullable=True)


def upgrade() -> None:
    op.create_table(
        "work_orders",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("order_type", sa.String(length=16), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("operation_number", sa.String(length=32), nullable=False, unique=True),
        sa.Column("rework_kind", sa.String(length=16), nullable=True),
        sa.Column(
            "related_order_id", sa.Integer(), sa.ForeignKey("work_orders.id"), nullable=True
        ),
        sa.Column("client_id", sa.Integer(), sa.ForeignKey("clients.id"), nullable=True),
        sa.Column(
            "razon_social_id", sa.Integer(), sa.ForeignKey("razones_sociales.id"),
            nullable=False,
        ),
        sa.Column("site_id", sa.Integer(), sa.ForeignKey("sites.id"), nullable=False),
        sa.Column("order_date", sa.Date(), nullable=False),
        sa.Column(
            "finished_product_id", sa.Integer(), sa.ForeignKey("products.id"), nullable=False
        ),
        sa.Column("finished_code", sa.String(length=64), nullable=False),
        sa.Column("finished_name", sa.String(length=200), nullable=False),
        sa.Column("finished_provider", sa.String(length=200), nullable=False),
        sa.Column("finished_presentation", sa.String(length=64), nullable=False),
        sa.Column("finished_liters", sa.Numeric(12, 2), nullable=False),
        sa.Column("barcode_mode", sa.String(length=16), nullable=False),
        sa.Column("labels_planned", sa.Integer(), nullable=True),
        sa.Column("labels_actual", sa.Integer(), nullable=True),
        _user_fk("labels_actual_by"),
        sa.Column("labels_actual_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("previous_lot", sa.String(length=100), nullable=True),
        sa.Column("new_lot", sa.String(length=100), nullable=True),
        _user_fk("new_lot_by"),
        sa.Column("new_lot_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expiry_date", sa.Date(), nullable=True),
        _user_fk("expiry_set_by"),
        sa.Column("expiry_set_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("warnings", postgresql.JSONB(), nullable=False),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        _user_fk("closed_by"),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("close_note", sa.Text(), nullable=True),
        _user_fk("cancelled_by"),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancel_reason", sa.Text(), nullable=True),
        *_timestamps(),
        sa.CheckConstraint(_in("order_type", ("trabajo", "retrabajo")), name="ck_work_orders_type"),
        sa.CheckConstraint(_in("status", _STATUSES), name="ck_work_orders_status"),
        sa.CheckConstraint(
            "rework_kind IS NULL OR " + _in("rework_kind", ("previous_order", "own_stock")),
            name="ck_work_orders_rework_kind",
        ),
        sa.CheckConstraint(
            _in("barcode_mode", ("per_container", "per_box")),
            name="ck_work_orders_barcode_mode",
        ),
        sa.CheckConstraint("finished_liters > 0", name="ck_work_orders_finished_liters"),
        sa.UniqueConstraint("order_type", "sequence", name="uq_work_orders_type_sequence"),
    )
    for column in ("client_id", "razon_social_id", "site_id", "order_date",
                   "finished_product_id", "status"):
        op.create_index(f"ix_work_orders_{column}", "work_orders", [column])
    op.create_index("ix_work_orders_created_at", "work_orders", ["created_at"])

    op.create_table(
        "order_base_products",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "order_id", sa.Integer(), sa.ForeignKey("work_orders.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id"), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("provider", sa.String(length=200), nullable=False),
        sa.Column("presentation", sa.String(length=64), nullable=False),
        sa.Column("razon_social_code", sa.String(length=6), nullable=False),
        sa.Column("liters", sa.Numeric(12, 2), nullable=False),
        *_timestamps(),
        sa.UniqueConstraint("order_id", "product_id", name="uq_order_base_products_product"),
        sa.CheckConstraint("liters > 0", name="ck_order_base_products_liters"),
    )
    op.create_index("ix_order_base_products_order_id", "order_base_products", ["order_id"])
    op.create_index("ix_order_base_products_product_id", "order_base_products", ["product_id"])

    op.create_table(
        "order_packaging",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "order_id", sa.Integer(), sa.ForeignKey("work_orders.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "packaging_item_id", sa.Integer(), sa.ForeignKey("packaging_items.id"),
            nullable=False,
        ),
        sa.Column("planned_qty", sa.Integer(), nullable=False),
        sa.Column("actual_qty", sa.Integer(), nullable=True),
        _user_fk("actual_by"),
        sa.Column("actual_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.UniqueConstraint("order_id", "packaging_item_id", name="uq_order_packaging_item"),
        sa.CheckConstraint("planned_qty > 0", name="ck_order_packaging_planned"),
    )
    op.create_index("ix_order_packaging_order_id", "order_packaging", ["order_id"])

    op.create_table(
        "order_checklist",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "order_id", sa.Integer(), sa.ForeignKey("work_orders.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("item", sa.String(length=32), nullable=False),
        sa.Column("checked", sa.Boolean(), nullable=False),
        _user_fk("checked_by"),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.UniqueConstraint("order_id", "item", name="uq_order_checklist_item"),
        sa.CheckConstraint(_in("item", _CHECKLIST), name="ck_order_checklist_item"),
    )
    op.create_index("ix_order_checklist_order_id", "order_checklist", ["order_id"])

    op.create_table(
        "order_comments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "order_id", sa.Integer(), sa.ForeignKey("work_orders.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        *_timestamps(),
    )
    op.create_index("ix_order_comments_order_id", "order_comments", ["order_id"])

    op.create_table(
        "reservations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "order_id", sa.Integer(), sa.ForeignKey("work_orders.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("site_id", sa.Integer(), sa.ForeignKey("sites.id"), nullable=False),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id"), nullable=True),
        sa.Column(
            "packaging_item_id", sa.Integer(), sa.ForeignKey("packaging_items.id"),
            nullable=True,
        ),
        sa.Column("quantity", sa.Numeric(12, 2), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        *_timestamps(),
        sa.CheckConstraint(_ITEM_XOR, name="ck_reservations_item_xor"),
        sa.CheckConstraint(
            _in("status", ("active", "consumed", "released")), name="ck_reservations_status"
        ),
        sa.CheckConstraint("quantity > 0", name="ck_reservations_quantity"),
    )
    op.create_index("ix_reservations_order_id", "reservations", ["order_id"])
    op.create_index(
        "ix_reservations_site_product_status", "reservations",
        ["site_id", "product_id", "status"],
    )
    op.create_index(
        "ix_reservations_site_packaging_status", "reservations",
        ["site_id", "packaging_item_id", "status"],
    )

    # stock_movements.order_id was a plain integer in phase 1.
    op.create_foreign_key(
        "fk_stock_movements_order_id", "stock_movements", "work_orders", ["order_id"], ["id"]
    )


def downgrade() -> None:
    op.drop_constraint("fk_stock_movements_order_id", "stock_movements", type_="foreignkey")
    op.drop_table("reservations")
    op.drop_table("order_comments")
    op.drop_table("order_checklist")
    op.drop_table("order_packaging")
    op.drop_table("order_base_products")
    op.drop_table("work_orders")
