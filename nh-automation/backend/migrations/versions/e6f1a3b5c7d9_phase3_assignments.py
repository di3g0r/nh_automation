"""phase3 assignments: assignments, assignment_events, FK
stock_movements.assignment_id; deactivate operator users (v3.1)

Revision ID: e6f1a3b5c7d9
Revises: d4e8a1b2c3f5
Create Date: 2026-10-13

"""
from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "e6f1a3b5c7d9"
down_revision: Union[str, None] = "d4e8a1b2c3f5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Frozen copies (migrations must not depend on app code that may change later).
_STATUSES = ("pending", "running", "paused", "completed", "cancelled")
_EVENTS = ("assign", "start", "pause", "resume", "progress", "complete", "cancel", "error")
_SOURCES = ("plc", "manual")


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN (" + ", ".join(f"'{v}'" for v in values) + ")"


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "assignments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "order_id", sa.Integer(),
            sa.ForeignKey("work_orders.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("machine_id", sa.Integer(), sa.ForeignKey("machines.id"), nullable=False),
        sa.Column("planned_liters", sa.Numeric(12, 2), nullable=False),
        sa.Column("actual_liters", sa.Numeric(12, 2), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("queue_position", sa.Integer(), nullable=False),
        sa.Column("last_source", sa.String(length=8), nullable=True),
        sa.Column("assigned_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.UniqueConstraint("order_id", "machine_id", name="uq_assignments_order_machine"),
        sa.CheckConstraint(_in("status", _STATUSES), name="ck_assignments_status"),
        sa.CheckConstraint(
            "last_source IS NULL OR " + _in("last_source", _SOURCES),
            name="ck_assignments_last_source",
        ),
        sa.CheckConstraint("planned_liters > 0", name="ck_assignments_planned_liters"),
        sa.CheckConstraint(
            "actual_liters IS NULL OR actual_liters >= 0", name="ck_assignments_actual_liters"
        ),
    )
    op.create_index("ix_assignments_order_id", "assignments", ["order_id"])
    op.create_index("ix_assignments_machine_status", "assignments", ["machine_id", "status"])

    op.create_table(
        "assignment_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "assignment_id", sa.Integer(),
            sa.ForeignKey("assignments.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("event", sa.String(length=16), nullable=False),
        sa.Column("liters", sa.Numeric(12, 2), nullable=True),
        sa.Column("source", sa.String(length=8), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("machine_id", sa.Integer(), sa.ForeignKey("machines.id"), nullable=True),
        *_timestamps(),
        sa.CheckConstraint(_in("event", _EVENTS), name="ck_assignment_events_event"),
        sa.CheckConstraint(_in("source", _SOURCES), name="ck_assignment_events_source"),
    )
    op.create_index(
        "ix_assignment_events_assignment_id", "assignment_events", ["assignment_id"]
    )

    # stock_movements.assignment_id was a plain integer since phase 1.
    op.create_foreign_key(
        "fk_stock_movements_assignment_id", "stock_movements", "assignments",
        ["assignment_id"], ["id"],
    )

    # v3.1: operators do not use the platform. Keep the rows (and the role in
    # ck_users_role) but deactivate them, audited.
    conn = op.get_bind()
    now = datetime.now(UTC)
    rows = conn.execute(
        sa.text(
            "SELECT id, username, full_name FROM users "
            "WHERE role = 'operator' AND is_active = true"
        )
    ).all()
    for user_id, username, full_name in rows:
        conn.execute(
            sa.text("UPDATE users SET is_active = false, updated_at = :now WHERE id = :id"),
            {"id": user_id, "now": now},
        )
        snap = {"username": username, "full_name": full_name, "role": "operator"}
        conn.execute(
            sa.text(
                "INSERT INTO audit_log "
                "(user_id, entity, entity_id, action, before, after, created_at) "
                "VALUES (NULL, 'user', :id, 'deactivate', CAST(:before AS JSONB), "
                "CAST(:after AS JSONB), :now)"
            ),
            {
                "id": user_id,
                "before": json.dumps(snap | {"is_active": True}),
                "after": json.dumps(snap | {"is_active": False, "via": "migration:phase3"}),
                "now": now,
            },
        )
    # Their sessions stop working too.
    conn.execute(
        sa.text(
            "UPDATE sessions SET revoked_at = :now WHERE revoked_at IS NULL AND user_id IN "
            "(SELECT id FROM users WHERE role = 'operator')"
        ),
        {"now": now},
    )
    conn.execute(sa.text("DELETE FROM settings WHERE key = 'session_timeout_operator_hours'"))


def downgrade() -> None:
    # Operator users stay deactivated (reactivate them by hand if needed).
    op.get_bind().execute(
        sa.text(
            "INSERT INTO settings (key, value, created_at, updated_at) "
            "VALUES ('session_timeout_operator_hours', CAST('12' AS JSONB), now(), now()) "
            "ON CONFLICT (key) DO NOTHING"
        )
    )
    op.drop_constraint(
        "fk_stock_movements_assignment_id", "stock_movements", type_="foreignkey"
    )
    op.drop_table("assignment_events")
    op.drop_table("assignments")
