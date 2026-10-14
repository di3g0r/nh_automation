"""phase1b v2/v3 updates: production_manager role, razones_sociales,
order_sequences, products.razon_social_id, client seed correction, settings

Revision ID: c7d2f4a8b913
Revises: b1c4e2a9f301
Create Date: 2026-10-13

"""
from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "c7d2f4a8b913"
down_revision: Union[str, None] = "b1c4e2a9f301"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Frozen copies (migrations must not depend on app code that may change later).
_ROLES = ("master_admin", "admin", "production_manager", "operator")
# TODO(OPEN-16): RS3/RS4 are placeholders until the owner gives the real names.
_SEED_RAZONES = [
    ("NB", "NOBELTECH"),
    ("ANB", "AGRONB"),
    ("RS3", "Razón social 3 (por definir)"),
    ("RS4", "Razón social 4 (por definir)"),
]
_SEED_SEQUENCES = [("trabajo", "T"), ("retrabajo", "R")]


def _role_check(roles: tuple[str, ...]) -> str:
    return "role IN (" + ", ".join(f"'{r}'" for r in roles) + ")"


def convert_roles(conn: sa.engine.Connection, old: str, new: str) -> int:
    """Rename a role on every user. Plain SQL, so tests can run it on SQLite."""
    result = conn.execute(
        sa.text("UPDATE users SET role = :new WHERE role = :old"), {"new": new, "old": old}
    )
    return result.rowcount or 0


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    ]


def upgrade() -> None:
    conn = op.get_bind()
    now = datetime.now(UTC)

    # 1. Roles: supervisor -> production_manager, then forbid unknown roles.
    convert_roles(conn, "supervisor", "production_manager")
    op.create_check_constraint("ck_users_role", "users", _role_check(_ROLES))

    # 2. Razones sociales.
    op.create_table(
        "razones_sociales",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(length=6), nullable=False, unique=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        *_timestamps(),
    )
    for code, name in _SEED_RAZONES:
        conn.execute(
            sa.text(
                "INSERT INTO razones_sociales (code, name, is_active, created_at, updated_at) "
                "VALUES (:code, :name, true, :now, :now)"
            ),
            {"code": code, "name": name, "now": now},
        )

    # 3. Order sequences (BR-19).
    op.create_table(
        "order_sequences",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("order_type", sa.String(length=16), nullable=False, unique=True),
        sa.Column("prefix", sa.String(length=4), nullable=False),
        sa.Column("next_number", sa.Integer(), nullable=False),
        *_timestamps(),
        sa.CheckConstraint("next_number >= 1", name="ck_order_sequences_next_number"),
        sa.CheckConstraint(
            "order_type IN ('trabajo', 'retrabajo')", name="ck_order_sequences_order_type"
        ),
    )
    for order_type, prefix in _SEED_SEQUENCES:
        conn.execute(
            sa.text(
                "INSERT INTO order_sequences "
                "(order_type, prefix, next_number, created_at, updated_at) "
                "VALUES (:order_type, :prefix, 1, :now, :now)"
            ),
            {"order_type": order_type, "prefix": prefix, "now": now},
        )

    # 4. Products belong to a razón social (nullable for imported rows).
    op.add_column("products", sa.Column("razon_social_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_products_razon_social_id", "products", "razones_sociales",
        ["razon_social_id"], ["id"],
    )
    op.create_index("ix_products_razon_social_id", "products", ["razon_social_id"])

    # 5. NOBELTECH / AGRONB (codes NB, ANB) were seeded as clients by mistake in
    #    phase 1; they are razones sociales. Deactivate, never delete.
    rows = conn.execute(
        sa.text(
            "SELECT id, name, code FROM clients WHERE is_active = true AND code IN ('NB', 'ANB')"
        )
    ).all()
    for client_id, name, code in rows:
        conn.execute(
            sa.text("UPDATE clients SET is_active = false, updated_at = :now WHERE id = :id"),
            {"id": client_id, "now": now},
        )
        snap = {"name": name, "code": code}
        conn.execute(
            sa.text(
                "INSERT INTO audit_log "
                "(user_id, entity, entity_id, action, before, after, created_at) "
                "VALUES (NULL, 'client', :id, 'deactivate', CAST(:before AS JSONB), "
                "CAST(:after AS JSONB), :now)"
            ),
            {
                "id": client_id,
                "before": json.dumps(snap | {"is_active": True}),
                "after": json.dumps(snap | {"is_active": False, "via": "migration:phase1b"}),
                "now": now,
            },
        )

    # 6. Settings: no approval step any more; second tolerance (TODO(OPEN-19)).
    conn.execute(sa.text("DELETE FROM settings WHERE key = 'approver_must_differ'"))
    conn.execute(
        sa.text(
            "INSERT INTO settings (key, value, created_at, updated_at) "
            "VALUES ('difference_tolerance_percent', CAST('0' AS JSONB), :now, :now) "
            "ON CONFLICT (key) DO NOTHING"
        ),
        {"now": now},
    )


def downgrade() -> None:
    conn = op.get_bind()
    now = datetime.now(UTC)

    conn.execute(sa.text("DELETE FROM settings WHERE key = 'difference_tolerance_percent'"))
    conn.execute(
        sa.text(
            "INSERT INTO settings (key, value, created_at, updated_at) "
            "VALUES ('approver_must_differ', CAST('false' AS JSONB), :now, :now) "
            "ON CONFLICT (key) DO NOTHING"
        ),
        {"now": now},
    )
    conn.execute(
        sa.text(
            "UPDATE clients SET is_active = true, updated_at = :now "
            "WHERE code IN ('NB', 'ANB')"
        ),
        {"now": now},
    )

    op.drop_index("ix_products_razon_social_id", table_name="products")
    op.drop_constraint("fk_products_razon_social_id", "products", type_="foreignkey")
    op.drop_column("products", "razon_social_id")
    op.drop_table("order_sequences")
    op.drop_table("razones_sociales")

    op.drop_constraint("ck_users_role", "users", type_="check")
    convert_roles(conn, "production_manager", "supervisor")
