"""phase1 catalogs and inventory: sites, clients, products, packaging_items,
machines, stock_levels, stock_movements + base seed data (data model §5)

Revision ID: b1c4e2a9f301
Revises: 732ef7916919
Create Date: 2026-10-09

"""
from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "b1c4e2a9f301"
down_revision: Union[str, None] = "732ef7916919"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_ITEM_XOR = (
    "(product_id IS NOT NULL AND packaging_item_id IS NULL) OR "
    "(product_id IS NULL AND packaging_item_id IS NOT NULL)"
)

# Frozen copy of the production seed (data model §5). Kept inline on purpose:
# migrations must not change behavior if app code changes later.
_SEED_SITE = "ECOINDUSTRIAL PACÍFICO"
_SEED_CLIENTS = [("NOBELTECH", "NB"), ("AGRONB", "ANB")]
_SEED_PACKAGING = [
    ("ENVCO01005", "Envase 1 L liso Novapack", "envase"),
    ("ENVLI01004", "Envase 1 L corrugado", "envase"),
    ("ENVLI20001", "Envase 20 L Fisher", "envase"),
    ("ENVLI05003", "Envase 5 L Fisher", "envase"),
    ("ENVLI25007", "Envase 250 ml liso Novapack", "envase"),
    ("ENVCO25006", "Envase 250 ml corrugado", "envase"),
    ("BOLTE20008", "Bolsa termosellada 1 kg", "bolsa"),
    ("CAJ01FP007", "Caja Forcrop 12x1", "caja"),
    ("CAJ05FP006", "Caja Forcrop 4x5", "caja"),
    ("CAJ01BL003", "Caja blanca 12x1", "caja"),
    ("CAJ05BL004", "Caja blanca 4x5", "caja"),
    ("CAJ05BL005", "Caja blanca 0.250 grs", "caja"),
    ("CAJ01AZ002", "Caja azul 12x1", "caja"),
    ("CAJ05AZ001", "Caja azul 4x5", "caja"),
]


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "sites",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=200), nullable=False, unique=True),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        *_timestamps(),
    )

    op.create_table(
        "clients",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("code", sa.String(length=32), nullable=False, unique=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        *_timestamps(),
    )

    op.create_table(
        "products",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("provider", sa.String(length=200), nullable=False),
        sa.Column("presentation", sa.String(length=64), nullable=False),
        sa.Column("container_liters", sa.Numeric(12, 2), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        *_timestamps(),
    )
    op.create_index("ix_products_code", "products", ["code"], unique=True)

    op.create_table(
        "packaging_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("description", sa.String(length=200), nullable=False),
        sa.Column("category", sa.String(length=32), nullable=False),
        sa.Column("low_stock_threshold", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        *_timestamps(),
    )
    op.create_index("ix_packaging_items_code", "packaging_items", ["code"], unique=True)

    op.create_table(
        "machines",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(length=32), nullable=False, unique=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("site_id", sa.Integer(), sa.ForeignKey("sites.id"), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("in_maintenance", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("api_key_hash", sa.String(length=128), nullable=True, unique=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
    )

    op.create_table(
        "stock_levels",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("site_id", sa.Integer(), sa.ForeignKey("sites.id"), nullable=False),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id"), nullable=True),
        sa.Column(
            "packaging_item_id", sa.Integer(), sa.ForeignKey("packaging_items.id"), nullable=True
        ),
        sa.Column("on_hand", sa.Numeric(12, 2), nullable=False, server_default="0"),
        *_timestamps(),
        sa.CheckConstraint(_ITEM_XOR, name="ck_stock_levels_item_xor"),
        sa.UniqueConstraint("site_id", "product_id", name="uq_stock_levels_site_product"),
        sa.UniqueConstraint(
            "site_id", "packaging_item_id", name="uq_stock_levels_site_packaging"
        ),
    )
    op.create_index("ix_stock_levels_site_id", "stock_levels", ["site_id"])

    op.create_table(
        "stock_movements",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("site_id", sa.Integer(), sa.ForeignKey("sites.id"), nullable=False),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id"), nullable=True),
        sa.Column(
            "packaging_item_id", sa.Integer(), sa.ForeignKey("packaging_items.id"), nullable=True
        ),
        sa.Column("type", sa.String(length=32), nullable=False),
        sa.Column("quantity", sa.Numeric(12, 2), nullable=False),
        sa.Column("order_id", sa.Integer(), nullable=True),
        sa.Column("assignment_id", sa.Integer(), nullable=True),
        sa.Column(
            "user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column("note", sa.Text(), nullable=True),
        *_timestamps(),
        sa.CheckConstraint(_ITEM_XOR, name="ck_stock_movements_item_xor"),
    )
    op.create_index("ix_stock_movements_site_id", "stock_movements", ["site_id"])
    op.create_index("ix_stock_movements_product_id", "stock_movements", ["product_id"])
    op.create_index(
        "ix_stock_movements_packaging_item_id", "stock_movements", ["packaging_item_id"]
    )
    op.create_index("ix_stock_movements_order_id", "stock_movements", ["order_id"])
    op.create_index("ix_stock_movements_created_at", "stock_movements", ["created_at"])

    _seed()


def _seed() -> None:
    now = datetime.now(UTC)
    conn = op.get_bind()

    site_id = conn.execute(
        sa.text(
            "INSERT INTO sites (name, is_default, is_active, created_at, updated_at) "
            "VALUES (:name, true, true, :now, :now) RETURNING id"
        ),
        {"name": _SEED_SITE, "now": now},
    ).scalar_one()

    for name, code in _SEED_CLIENTS:
        conn.execute(
            sa.text(
                "INSERT INTO clients (name, code, is_active, created_at, updated_at) "
                "VALUES (:name, :code, true, :now, :now)"
            ),
            {"name": name, "code": code, "now": now},
        )

    for code, description, category in _SEED_PACKAGING:
        conn.execute(
            sa.text(
                "INSERT INTO packaging_items "
                "(code, description, category, low_stock_threshold, is_active, "
                "created_at, updated_at) "
                "VALUES (:code, :description, :category, 0, true, :now, :now)"
            ),
            {"code": code, "description": description, "category": category, "now": now},
        )

    # Keep the phase-0 `default_site_id` setting in sync with sites.is_default.
    conn.execute(
        sa.text(
            "INSERT INTO settings (key, value, created_at, updated_at) "
            "VALUES ('default_site_id', CAST(:value AS JSONB), :now, :now) "
            "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = :now"
        ),
        {"value": json.dumps(site_id), "now": now},
    )


def downgrade() -> None:
    op.drop_table("stock_movements")
    op.drop_table("stock_levels")
    op.drop_table("machines")
    op.drop_table("packaging_items")
    op.drop_table("products")
    op.drop_table("clients")
    op.drop_table("sites")
    op.execute(
        "UPDATE settings SET value = 'null'::jsonb WHERE key = 'default_site_id'"
    )
