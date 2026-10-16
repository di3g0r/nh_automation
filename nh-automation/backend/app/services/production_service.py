"""Read models for phase 3: assignment rows with allowed actions, the
difference (BR-12), the Producción sections (FR-PM-1), the machine board
(FR-MCH-1) and machine queues (FR-ASG-3). No writes here."""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import not_found
from app.models.assignments import Assignment
from app.models.catalogs import Client, Machine, RazonSocial
from app.models.orders import WorkOrder
from app.models.plc import PlcEvent
from app.models.user import User
from app.schemas.production import (
    AssignmentOut,
    DifferenceOut,
    MachineBoardItem,
    MachineQueueOut,
    MachineState,
    MissingForAssign,
    PlcErrorOut,
    ProductionOrder,
)
from app.services import settings_service
from app.services.assignment_service import (
    MachineQueue,
    actual_total,
    machine_queues,
    order_assignments,
    planned_total,
    start_blocked_reason,
)

TO_ASSIGN_STATUSES = ("created",)
IN_PRODUCTION_STATUSES = ("assigned", "in_progress", "paused")
TO_CLOSE_STATUSES = ("completed",)
ENDED_STATUSES = frozenset({"completed", "closed"})


# Difference (BR-12) ---------------------------------------------------------------


def _setting_decimal(db: Session, key: str) -> Decimal:
    return Decimal(str(settings_service.get_value(db, key) or 0))


def difference(db: Session, order: WorkOrder, assignments: Sequence[Assignment]) -> DifferenceOut:
    """actual - ordered. Within range if |d| <= tolerance liters OR <= tolerance
    percent of the ordered liters. TODO(OPEN-19): range undecided; never blocks."""
    ordered = Decimal(order.finished_liters)
    actual = actual_total(assignments)
    diff = actual - ordered
    tol_liters = _setting_decimal(db, "difference_tolerance_liters")
    tol_percent = _setting_decimal(db, "difference_tolerance_percent")
    within = abs(diff) <= tol_liters or abs(diff) <= ordered * tol_percent / Decimal(100)
    return DifferenceOut(
        ordered_liters=ordered, actual_liters=actual, difference=diff, within_range=within
    )


# Assignment rows ------------------------------------------------------------------------


def _names(db: Session, ids: set[int]) -> dict[int, str]:
    if not ids:
        return {}
    return {uid: name for uid, name in db.query(User.id, User.full_name).filter(User.id.in_(ids))}


def assignment_rows(db: Session, assignments: Sequence[Assignment]) -> list[AssignmentOut]:
    """AssignmentOut for each row, with the actions allowed right now."""
    if not assignments:
        return []
    orders = {
        o.id: o
        for o in db.query(WorkOrder).filter(
            WorkOrder.id.in_({a.order_id for a in assignments})
        )
    }
    machines = {a.machine_id: a.machine for a in assignments}
    queues = machine_queues(db, list(machines.values()))
    names = _names(db, {a.assigned_by for a in assignments})
    out: list[AssignmentOut] = []
    for a in assignments:
        order = orders[a.order_id]
        queue: MachineQueue = queues[a.machine_id]
        reason = (
            start_blocked_reason(a, order.status, queue) if a.status == "pending" else None
        )
        out.append(
            AssignmentOut(
                id=a.id,
                order_id=order.id,
                operation_number=order.operation_number,
                order_type=order.order_type,  # type: ignore[arg-type]
                order_status=order.status,  # type: ignore[arg-type]
                finished_code=order.finished_code,
                finished_name=order.finished_name,
                machine_id=a.machine_id,
                machine_code=a.machine.code,
                machine_name=a.machine.name,
                planned_liters=a.planned_liters,
                actual_liters=a.actual_liters,
                status=a.status,  # type: ignore[arg-type]
                queue_position=a.queue_position,
                last_source=a.last_source,  # type: ignore[arg-type]
                assigned_by_name=names.get(a.assigned_by, ""),
                assigned_at=a.assigned_at,
                started_at=a.started_at,
                completed_at=a.completed_at,
                can_start=a.status == "pending" and reason is None,
                can_pause=a.status == "running",
                can_resume=a.status == "paused" and not a.machine.in_maintenance,
                can_complete=a.status in ("running", "paused"),
                start_blocked_reason=reason,
            )
        )
    return out


# Producción sections (FR-PM-1) ------------------------------------------------------------


def missing_for_assign(
    order: WorkOrder, assignments: Sequence[Assignment]
) -> list[MissingForAssign]:
    missing: list[MissingForAssign] = []
    if order.expiry_date is None:
        missing.append("expiry")
    live = [a for a in assignments if a.status != "cancelled"]
    if not live or planned_total(live) != Decimal(order.finished_liters):
        missing.append("machines")
    return missing


def _production_orders(
    db: Session, statuses: Sequence[str], *, newest_first: bool
) -> list[ProductionOrder]:
    query = (
        db.query(WorkOrder, Client.name, RazonSocial.code)
        .outerjoin(Client, Client.id == WorkOrder.client_id)
        .join(RazonSocial, RazonSocial.id == WorkOrder.razon_social_id)
        .filter(WorkOrder.status.in_(statuses))
    )
    order_by = WorkOrder.created_at.desc() if newest_first else WorkOrder.created_at.asc()
    rows = query.order_by(order_by, WorkOrder.id).all()
    out: list[ProductionOrder] = []
    for order, client_name, rs_code in rows:
        assignments = order_assignments(db, order.id, include_cancelled=False)
        out.append(
            ProductionOrder(
                id=order.id,
                operation_number=order.operation_number,
                order_type=order.order_type,  # type: ignore[arg-type]
                status=order.status,  # type: ignore[arg-type]
                client_name=client_name,
                razon_social_code=rs_code,
                finished_code=order.finished_code,
                finished_name=order.finished_name,
                finished_liters=order.finished_liters,
                expiry_date=order.expiry_date,
                created_at=order.created_at,
                missing=missing_for_assign(order, assignments) if order.status == "created" else [],
                assigned_liters=planned_total(assignments),
                assignments=assignment_rows(db, assignments),
                difference=(
                    difference(db, order, assignments) if order.status in ENDED_STATUSES else None
                ),
            )
        )
    return out


def to_assign(db: Session) -> list[ProductionOrder]:
    """Por asignar: orders in Creada, newest first."""
    return _production_orders(db, TO_ASSIGN_STATUSES, newest_first=True)


def in_production(db: Session) -> list[ProductionOrder]:
    """En producción: Asignada, En proceso, Pausada (oldest first: work order)."""
    return _production_orders(db, IN_PRODUCTION_STATUSES, newest_first=False)


def to_close(db: Session) -> list[ProductionOrder]:
    """Por cerrar: Completada, oldest first."""
    return _production_orders(db, TO_CLOSE_STATUSES, newest_first=False)


# Machine board / queues ---------------------------------------------------------------


def machine_state(machine: Machine, queue: MachineQueue) -> MachineState:
    if machine.in_maintenance:
        return "maintenance"
    if queue.active is not None:
        return "busy" if queue.active.status == "running" else "paused"
    return "free"


def latest_plc_errors(db: Session, machine_ids: Sequence[int]) -> dict[int, PlcErrorOut]:
    """The latest applied `error` event of each machine's PLC (phase 4)."""
    if not machine_ids:
        return {}
    latest = (
        select(func.max(PlcEvent.id))
        .where(
            PlcEvent.machine_id.in_(machine_ids),
            PlcEvent.event == "error",
            PlcEvent.result == "applied",
        )
        .group_by(PlcEvent.machine_id)
    )
    rows = (
        db.query(PlcEvent, WorkOrder.operation_number)
        .outerjoin(Assignment, Assignment.id == PlcEvent.assignment_id)
        .outerjoin(WorkOrder, WorkOrder.id == Assignment.order_id)
        .filter(PlcEvent.id.in_(latest))
        .all()
    )
    return {
        e.machine_id: PlcErrorOut(
            error_code=e.error_code, message=e.message, received_at=e.received_at,
            operation_number=operation_number,
        )
        for e, operation_number in rows
    }


def board(db: Session) -> list[MachineBoardItem]:
    """FR-MCH-1: one card per active machine."""
    machines = (
        db.query(Machine).filter(Machine.is_active.is_(True)).order_by(Machine.code).all()
    )
    queues = machine_queues(db, machines)
    shown = [
        a
        for q in queues.values()
        for a in (q.active, q.next_ready)
        if a is not None
    ]
    rows = {r.id: r for r in assignment_rows(db, shown)}
    errors = latest_plc_errors(db, [m.id for m in machines])
    out: list[MachineBoardItem] = []
    for m in machines:
        q = queues[m.id]
        out.append(
            MachineBoardItem(
                id=m.id,
                code=m.code,
                name=m.name,
                site_name=m.site.name,
                in_maintenance=m.in_maintenance,
                state=machine_state(m, q),
                current=rows[q.active.id] if q.active else None,
                queue_length=len(q.pending),
                next_assignment=rows[q.next_ready.id] if q.next_ready else None,
                has_plc_login=m.plc_db_username is not None,
                plc_last_seen_at=m.last_seen_at,
                plc_last_error=errors.get(m.id),
            )
        )
    return out


def machine_queue(db: Session, machine_id: int) -> MachineQueueOut:
    """FR-ASG-3: the current assignment and the pending ones in queue order
    (this is what the PLC screen shows from phase 4)."""
    machine = db.get(Machine, machine_id)
    if machine is None:
        raise not_found("Máquina")
    q = machine_queues(db, [machine])[machine.id]
    rows = assignment_rows(db, ([q.active] if q.active else []) + q.pending)
    by_id = {r.id: r for r in rows}
    return MachineQueueOut(
        machine_id=machine.id,
        machine_code=machine.code,
        state=machine_state(machine, q),
        current=by_id[q.active.id] if q.active else None,
        pending=[by_id[a.id] for a in q.pending],
    )
