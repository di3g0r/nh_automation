"""phase4 PLC database interface: machines.plc_db_username, assignment_events
error columns, plc_events inbox + trigger, PLC views, group role plc_machine

Revision ID: f2a7c9d1e3b4
Revises: e6f1a3b5c7d9
Create Date: 2026-10-15

Needs a database user that can create roles (the Docker image's POSTGRES_USER
is a superuser). Roles are cluster-wide: the downgrade drops this database's
objects and grants but leaves the `plc_machine` role and the per-machine
logins in place (another database of the cluster may use them).
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "f2a7c9d1e3b4"
down_revision: Union[str, None] = "e6f1a3b5c7d9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Frozen copies (migrations must not depend on app code that may change later).
_EVENTS = ("start", "progress", "pause", "resume", "complete", "error")
_RESULTS = ("applied", "duplicate", "rejected")
_PLC_COLUMNS = "assignment_id, event, liters, seq, error_code, message, plc_timestamp"
_VIEWS = ("plc_assignment_packaging", "plc_assignment_base_products", "plc_pending_assignments")


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN (" + ", ".join(f"'{v}'" for v in values) + ")"


_TRIGGER_FUNCTION = f"""
CREATE FUNCTION plc_events_before_insert() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public AS $$
DECLARE
    v_machine_id integer;
BEGIN
    -- SECURITY DEFINER: current_user is the owner here; session_user is the PLC login.
    SELECT id INTO v_machine_id FROM machines
     WHERE plc_db_username = session_user AND is_active;
    IF v_machine_id IS NULL THEN
        RAISE EXCEPTION 'El usuario % no corresponde a una maquina activa', session_user
            USING ERRCODE = 'insufficient_privilege';
    END IF;
    IF NEW.event IS NULL OR NEW.event NOT IN ({", ".join(f"'{e}'" for e in _EVENTS)}) THEN
        RAISE EXCEPTION 'Evento no valido: %', NEW.event USING ERRCODE = 'check_violation';
    END IF;
    IF NEW.liters IS NOT NULL AND NEW.liters < 0 THEN
        RAISE EXCEPTION 'Los litros no pueden ser negativos' USING ERRCODE = 'check_violation';
    END IF;
    NEW.machine_id := v_machine_id;
    NEW.received_at := now();
    NEW.created_at := now();
    NEW.updated_at := now();
    NEW.processed_at := NULL;
    NEW.result := NULL;
    NEW.reject_reason := NULL;
    UPDATE machines SET last_seen_at = now() WHERE id = v_machine_id;
    -- Delivered on commit; wakes the backend event processor.
    PERFORM pg_notify('plc_events', v_machine_id::text);
    RETURN NEW;
END;
$$
"""

# Each PLC sees only its own machine (current_user = the PLC login: views
# keep the caller as current_user and read the base tables with the owner's
# rights, so PLC roles need no rights on business tables). Only orders with an
# expiry date (BR-20) and not-finished assignments. `queue_position` is
# renumbered 1..n: 1 = the running/paused assignment, or the next to start.
_PENDING_VIEW = """
CREATE VIEW plc_pending_assignments WITH (security_barrier) AS
SELECT
    a.id AS assignment_id,
    o.operation_number,
    o.order_type,
    CAST(row_number() OVER (
        ORDER BY (a.status = 'pending'), a.queue_position, a.id
    ) AS integer) AS queue_position,
    a.status,
    o.finished_code,
    o.finished_name,
    o.finished_presentation,
    a.planned_liters,
    a.actual_liters,
    o.expiry_date,
    o.labels_planned,
    o.barcode_mode,
    (SELECT string_agg(c.text, ' | ' ORDER BY c.created_at DESC, c.id DESC)
       FROM order_comments c WHERE c.order_id = o.id) AS comments
FROM assignments a
JOIN machines m ON m.id = a.machine_id
JOIN work_orders o ON o.id = a.order_id
WHERE m.plc_db_username = current_user
  AND m.is_active
  AND a.status IN ('pending', 'running', 'paused')
  AND o.status IN ('assigned', 'in_progress', 'paused')
  AND o.expiry_date IS NOT NULL
ORDER BY 4
"""

_BASE_PRODUCTS_VIEW = """
CREATE VIEW plc_assignment_base_products WITH (security_barrier) AS
SELECT
    p.assignment_id,
    b.position,
    b.code AS base_code,
    b.name AS base_name,
    round(b.liters * a.planned_liters / o.finished_liters, 2) AS liters
FROM plc_pending_assignments p
JOIN assignments a ON a.id = p.assignment_id
JOIN work_orders o ON o.id = a.order_id
JOIN order_base_products b ON b.order_id = o.id
ORDER BY p.queue_position, b.position
"""

_PACKAGING_VIEW = """
CREATE VIEW plc_assignment_packaging WITH (security_barrier) AS
SELECT
    p.assignment_id,
    i.code AS packaging_code,
    i.description AS packaging_description,
    op.planned_qty,
    p.labels_planned,
    p.barcode_mode
FROM plc_pending_assignments p
JOIN assignments a ON a.id = p.assignment_id
JOIN order_packaging op ON op.order_id = a.order_id
JOIN packaging_items i ON i.id = op.packaging_item_id
ORDER BY p.queue_position, i.code
"""


def upgrade() -> None:
    op.add_column("machines", sa.Column("plc_db_username", sa.String(length=63), nullable=True))
    op.create_unique_constraint("uq_machines_plc_db_username", "machines", ["plc_db_username"])
    op.add_column("assignment_events", sa.Column("error_code", sa.String(length=64), nullable=True))
    op.add_column("assignment_events", sa.Column("message", sa.Text(), nullable=True))

    op.create_table(
        "plc_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("machine_id", sa.Integer(), sa.ForeignKey("machines.id"), nullable=False),
        sa.Column("assignment_id", sa.Integer(), nullable=True),
        sa.Column("event", sa.String(length=16), nullable=False),
        sa.Column("liters", sa.Numeric(12, 2), nullable=True),
        sa.Column("seq", sa.BigInteger(), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("plc_timestamp", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "received_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("result", sa.String(length=16), nullable=True),
        sa.Column("reject_reason", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(_in("event", _EVENTS), name="ck_plc_events_event"),
        sa.CheckConstraint(
            "result IS NULL OR " + _in("result", _RESULTS), name="ck_plc_events_result"
        ),
        sa.CheckConstraint("liters IS NULL OR liters >= 0", name="ck_plc_events_liters"),
    )
    op.create_index(
        "ix_plc_events_unprocessed", "plc_events", ["received_at", "id"],
        postgresql_where=sa.text("processed_at IS NULL"),
    )
    op.create_index("ix_plc_events_machine_seq", "plc_events", ["machine_id", "seq"])
    op.create_index(
        "ix_plc_events_machine_event", "plc_events", ["machine_id", "event", "id"]
    )

    op.execute(_TRIGGER_FUNCTION)
    op.execute("REVOKE ALL ON FUNCTION plc_events_before_insert() FROM PUBLIC")
    op.execute(
        "CREATE TRIGGER plc_events_before_insert BEFORE INSERT ON plc_events "
        "FOR EACH ROW EXECUTE FUNCTION plc_events_before_insert()"
    )

    op.execute(_PENDING_VIEW)
    op.execute(_BASE_PRODUCTS_VIEW)
    op.execute(_PACKAGING_VIEW)

    # Group role (cluster-wide, may already exist from another database).
    op.execute(
        "DO $$ BEGIN "
        "IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'plc_machine') THEN "
        "CREATE ROLE plc_machine NOLOGIN; END IF; END $$"
    )
    op.execute(
        "DO $$ BEGIN EXECUTE format('GRANT CONNECT ON DATABASE %I TO plc_machine', "
        "current_database()); END $$"
    )
    op.execute("GRANT USAGE ON SCHEMA public TO plc_machine")
    for view in _VIEWS:
        op.execute(f"GRANT SELECT ON {view} TO plc_machine")
    op.execute(f"GRANT INSERT ({_PLC_COLUMNS}) ON plc_events TO plc_machine")
    op.execute("GRANT USAGE ON SEQUENCE plc_events_id_seq TO plc_machine")


def downgrade() -> None:
    op.execute("REVOKE ALL ON SEQUENCE plc_events_id_seq FROM plc_machine")
    op.execute("REVOKE ALL ON plc_events FROM plc_machine")
    for view in _VIEWS:
        op.execute(f"DROP VIEW {view}")
    op.execute(
        "DO $$ BEGIN EXECUTE format('REVOKE CONNECT ON DATABASE %I FROM plc_machine', "
        "current_database()); END $$"
    )
    op.execute("REVOKE USAGE ON SCHEMA public FROM plc_machine")
    op.drop_table("plc_events")  # drops the trigger too
    op.execute("DROP FUNCTION plc_events_before_insert()")
    op.drop_column("assignment_events", "message")
    op.drop_column("assignment_events", "error_code")
    op.drop_constraint("uq_machines_plc_db_username", "machines", type_="unique")
    op.drop_column("machines", "plc_db_username")
