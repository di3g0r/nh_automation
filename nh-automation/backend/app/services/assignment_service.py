"""Machine assignments and production actions (phase 3).

Business rules implemented here (data model §3/§4): BR-6 (assignment and
order transitions), BR-7 (machine split), BR-8/9/10 (completion stock
movements and reservations), BR-14 (one running/paused assignment per
machine, queue order), BR-20 (no start without expiry), BR-23 (pause/resume).

Every production action takes an `Actor`: a platform user (`source="manual"`)
or, from phase 4, a machine's PLC (`source="plc"`). The phase-4 event
processor calls `start`/`pause`/`resume`/`complete` with `Actor.plc(machine)`
so the rules stay in one place. Public writes commit once at the end unless
`commit=False` (then the caller owns the transaction).

Order status after `assigned` is derived from its assignments and recomputed
in the same transaction as every assignment change (data model §3).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Literal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import AppError, not_found
from app.core.timezone import utc_now
from app.models.assignments import Assignment, AssignmentEvent
from app.models.catalogs import Machine
from app.models.orders import Reservation, WorkOrder
from app.models.stock import StockMovement
from app.models.user import User
from app.schemas.production import AssignmentIn
from app.services import audit_service, reservation_service, stock_service
from app.services.reservation_service import format_liters
from app.services.stock_service import ItemRef

ORDER_AUDIT_ENTITY = "work_order"
TWO_PLACES = Decimal("0.01")

# Orders whose split can still change (BR-7, FR-ASG-2).
PRE_PRODUCTION_STATUSES = frozenset({"created", "assigned"})
# Orders whose pending assignments may start (expiry set + split complete, BR-20).
READY_STATUSES = frozenset({"assigned", "in_progress", "paused"})
# Orders whose status is derived from their assignments (data model §3).
DERIVED_STATUSES = frozenset({"assigned", "in_progress", "paused"})
ACTIVE_ASSIGNMENT_STATUSES = ("running", "paused")  # occupy the machine (BR-14)
OPEN_ASSIGNMENT_STATUSES = ("pending", "running", "paused")


@dataclass(frozen=True)
class Actor:
    """Who performed a production action: a platform user or a machine's PLC."""

    source: Literal["manual", "plc"]
    user: User | None = None
    machine: Machine | None = None

    @classmethod
    def manual(cls, user: User) -> Actor:
        return cls("manual", user=user)

    @classmethod
    def plc(cls, machine: Machine) -> Actor:
        return cls("plc", machine=machine)


def _q(value: Decimal) -> Decimal:
    return Decimal(value).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


def _conflict(code: str, message: str, details: dict[str, Any] | None = None) -> AppError:
    return AppError(code, message, 409, details)


def _invalid(code: str, message: str, details: dict[str, Any] | None = None) -> AppError:
    return AppError(code, message, 422, details)


# Loading ------------------------------------------------------------------------


def get_assignment(db: Session, assignment_id: int) -> Assignment:
    assignment = db.get(Assignment, assignment_id)
    if assignment is None:
        raise not_found("Asignación")
    return assignment


def _lock_order(db: Session, order_id: int) -> WorkOrder:
    order = db.query(WorkOrder).filter(WorkOrder.id == order_id).with_for_update().first()
    if order is None:
        raise not_found("Orden")
    return order


def _lock_machine(db: Session, machine_id: int) -> Machine:
    """Serializes production actions per machine (BR-14). Always taken after
    the order lock, so two actions never wait on each other in a cycle."""
    machine = db.query(Machine).filter(Machine.id == machine_id).with_for_update().first()
    if machine is None:
        raise not_found("Máquina")
    return machine


def order_assignments(
    db: Session, order_id: int, *, include_cancelled: bool = True
) -> list[Assignment]:
    query = db.query(Assignment).filter(Assignment.order_id == order_id)
    if not include_cancelled:
        query = query.filter(Assignment.status != "cancelled")
    return query.order_by(Assignment.id).all()


def machine_open_assignments(db: Session, machine_ids: Sequence[int]) -> list[Assignment]:
    """Pending, running and paused assignments of the machines, queue order."""
    if not machine_ids:
        return []
    return (
        db.query(Assignment)
        .filter(
            Assignment.machine_id.in_(machine_ids),
            Assignment.status.in_(OPEN_ASSIGNMENT_STATUSES),
        )
        .order_by(Assignment.machine_id, Assignment.queue_position, Assignment.id)
        .all()
    )


@dataclass
class MachineQueue:
    """Snapshot of one machine's queue, used for start checks and read models."""

    machine: Machine
    active: Assignment | None  # running or paused (BR-14: at most one)
    pending: list[Assignment]  # queue order
    next_ready: Assignment | None  # first pending whose order is ready (BR-20)


def machine_queues(db: Session, machines: Sequence[Machine]) -> dict[int, MachineQueue]:
    by_machine: dict[int, list[Assignment]] = {m.id: [] for m in machines}
    rows = machine_open_assignments(db, [m.id for m in machines])
    order_ids = {a.order_id for a in rows}
    statuses: dict[int, str] = {}
    if order_ids:
        for order_id, status in db.query(WorkOrder.id, WorkOrder.status).filter(
            WorkOrder.id.in_(order_ids)
        ):
            statuses[order_id] = status
    for a in rows:
        by_machine[a.machine_id].append(a)
    out: dict[int, MachineQueue] = {}
    for m in machines:
        items = by_machine[m.id]
        active = next((a for a in items if a.status in ACTIVE_ASSIGNMENT_STATUSES), None)
        pending = [a for a in items if a.status == "pending"]
        next_ready = next(
            (a for a in pending if statuses.get(a.order_id, "") in READY_STATUSES), None
        )
        out[m.id] = MachineQueue(machine=m, active=active, pending=pending, next_ready=next_ready)
    return out


def start_blocked_reason(
    assignment: Assignment, order_status: str, queue: MachineQueue
) -> str | None:
    """Why a pending assignment cannot start now (Spanish), or None (BR-14, BR-20)."""
    machine = queue.machine
    if order_status not in READY_STATUSES:
        return "La orden no está asignada: falta la fecha de caducidad o asignar máquinas."
    if not machine.is_active:
        return f"La máquina {machine.code} está inactiva."
    if machine.in_maintenance:
        return f"La máquina {machine.code} está en mantenimiento."
    if queue.active is not None and queue.active.id != assignment.id:
        return f"La máquina {machine.code} está ocupada con otra orden."
    if queue.next_ready is not None and queue.next_ready.id != assignment.id:
        return f"Hay otra orden antes en la fila de la máquina {machine.code}."
    return None


# Order status --------------------------------------------------------------------


def _live(assignments: Sequence[Assignment]) -> list[Assignment]:
    return [a for a in assignments if a.status != "cancelled"]


def planned_total(assignments: Sequence[Assignment]) -> Decimal:
    return sum((Decimal(a.planned_liters) for a in _live(assignments)), Decimal(0))


def actual_total(assignments: Sequence[Assignment]) -> Decimal:
    return sum(
        (Decimal(a.actual_liters) for a in _live(assignments) if a.actual_liters is not None),
        Decimal(0),
    )


def refresh_pre_production_status(db: Session, order: WorkOrder) -> str:
    """created <-> assigned: assigned once the expiry is set AND the split adds
    up exactly to the order liters (BR-7, BR-20). Returns the new status."""
    if order.status not in PRE_PRODUCTION_STATUSES:
        return order.status
    live = order_assignments(db, order.id, include_cancelled=False)
    ready = (
        order.expiry_date is not None
        and bool(live)
        and planned_total(live) == Decimal(order.finished_liters)
    )
    order.status = "assigned" if ready else "created"
    db.flush()
    return order.status


def derived_status(assignments: Sequence[Assignment]) -> str | None:
    """Data model §3. None while nothing has started (the order stays assigned)."""
    live = _live(assignments)
    if any(a.status == "running" for a in live):
        return "in_progress"
    if live and all(a.status == "completed" for a in live):
        return "completed"
    if any(a.started_at is not None for a in live):
        return "paused"
    return None


def _sync_order_status(db: Session, order: WorkOrder, actor: Actor) -> str:
    """Recompute a started order's status; completing it moves packaging and
    releases what is left reserved (BR-8, BR-10)."""
    if order.status not in DERIVED_STATUSES:
        return order.status
    new = derived_status(order_assignments(db, order.id)) or "assigned"
    if new == "completed":
        _complete_order(db, order, actor)
    order.status = new
    db.flush()
    return new


# Audit / events -------------------------------------------------------------------


def _actor_info(actor: Actor) -> dict[str, Any]:
    info: dict[str, Any] = {"source": actor.source}
    if actor.machine is not None:
        info["plc_machine"] = actor.machine.code
    return info


def _event(
    db: Session, assignment: Assignment, event: str, actor: Actor,
    liters: Decimal | None = None,
) -> None:
    db.add(
        AssignmentEvent(
            assignment_id=assignment.id, event=event, liters=liters, source=actor.source,
            user_id=actor.user.id if actor.user else None,
            machine_id=actor.machine.id if actor.machine else None,
        )
    )


def _audit_order(
    db: Session, order: WorkOrder, action: str, actor: Actor | User,
    before: dict[str, Any] | None, after: dict[str, Any] | None,
) -> None:
    user = actor if isinstance(actor, User) else actor.user
    audit_service.record(
        db, user=user, entity=ORDER_AUDIT_ENTITY, entity_id=order.id, action=action,
        before=before, after=after,
    )


def _split_snapshot(assignments: Sequence[Assignment]) -> list[dict[str, Any]]:
    return [
        {"machine": a.machine.code, "liters": str(_q(a.planned_liters))}
        for a in sorted(_live(assignments), key=lambda a: a.machine.code)
    ]


# Split (BR-7) ----------------------------------------------------------------------


def _next_queue_position(db: Session, machine_id: int) -> int:
    current = db.execute(
        select(func.max(Assignment.queue_position)).where(
            Assignment.machine_id == machine_id,
            Assignment.status.in_(OPEN_ASSIGNMENT_STATUSES),
        )
    ).scalar()
    return int(current or 0) + 1


def set_assignments(
    db: Session, order_id: int, items: Sequence[AssignmentIn], *, actor: User
) -> WorkOrder:
    """Replace the whole split before production starts (FR-ASG-1/2).

    The planned liters must add up exactly to the order's finished liters
    (BR-7); an empty list removes every assignment. Machines kept in the new
    split keep their queue position.
    """
    order = _lock_order(db, order_id)
    if order.status not in PRE_PRODUCTION_STATUSES:
        raise _conflict(
            "ASSIGNMENTS_LOCKED",
            "Las asignaciones ya no se pueden cambiar: la producción ya inició o la orden "
            "está cerrada o cancelada.",
            {"status": order.status},
        )
    wanted: dict[int, Decimal] = {}
    machines: dict[int, Machine] = {}
    for item in items:
        if item.machine_id in wanted:
            raise _invalid(
                "DUPLICATE_MACHINE", "Cada máquina solo puede aparecer una vez en la orden.",
                {"machine_id": item.machine_id},
            )
        machine = db.get(Machine, item.machine_id)
        if machine is None:
            raise not_found("Máquina")
        if not machine.is_active:
            raise _invalid(
                "MACHINE_INACTIVE", f"La máquina {machine.code} está inactiva.",
                {"machine_id": machine.id},
            )
        if machine.in_maintenance:
            raise _invalid(
                "MACHINE_IN_MAINTENANCE", f"La máquina {machine.code} está en mantenimiento.",
                {"machine_id": machine.id},
            )
        wanted[machine.id] = _q(item.planned_liters)
        machines[machine.id] = machine

    total = sum(wanted.values(), Decimal(0))
    ordered = _q(order.finished_liters)
    if wanted and total != ordered:
        raise _invalid(
            "SPLIT_MISMATCH",
            f"La suma asignada ({format_liters(total)}) debe ser exactamente igual a los "
            f"litros de la orden ({format_liters(ordered)}).",
            {"assigned": str(total), "ordered": str(ordered)},
        )

    current = order_assignments(db, order.id, include_cancelled=False)
    before = {"assignments": _split_snapshot(current), "status": order.status}
    now = utc_now()
    existing = {a.machine_id: a for a in current}
    for machine_id, assignment in existing.items():
        if machine_id not in wanted:
            db.delete(assignment)  # pending only (nothing started): events cascade
    db.flush()
    manual = Actor.manual(actor)
    for machine_id, liters in wanted.items():
        kept = existing.get(machine_id)
        if kept is not None:
            if _q(kept.planned_liters) != liters:
                kept.planned_liters = liters
                kept.assigned_by = actor.id
                kept.assigned_at = now
                _event(db, kept, "assign", manual, liters)
            continue
        assignment = Assignment(
            order_id=order.id, machine_id=machine_id, planned_liters=liters,
            status="pending", queue_position=_next_queue_position(db, machine_id),
            assigned_by=actor.id, assigned_at=now,
        )
        db.add(assignment)
        db.flush()
        _event(db, assignment, "assign", manual, liters)
    db.flush()

    refresh_pre_production_status(db, order)
    after_rows = order_assignments(db, order.id, include_cancelled=False)
    after = {"assignments": _split_snapshot(after_rows), "status": order.status}
    if after != before:
        _audit_order(db, order, "assign", actor, before, after)
    db.commit()
    db.refresh(order)
    return order


def delete_for_edit(db: Session, order: WorkOrder) -> list[dict[str, Any]]:
    """BR-16: products/liters changed before production -> the split is
    deleted (the caller audits and returns the order to Creada). No commit."""
    rows = order_assignments(db, order.id)
    removed = _split_snapshot(rows)
    for a in rows:
        db.delete(a)
    db.flush()
    return removed


def cancel_for_order(db: Session, order: WorkOrder, actor: User) -> int:
    """Order cancelled before production: pending assignments -> cancelled. No commit."""
    count = 0
    manual = Actor.manual(actor)
    for a in order_assignments(db, order.id, include_cancelled=False):
        if a.status == "pending":
            a.status = "cancelled"
            a.last_source = "manual"
            _event(db, a, "cancel", manual)
            count += 1
    db.flush()
    return count


# Queue (FR-ASG-3) -------------------------------------------------------------------


def reorder(db: Session, assignment_id: int, position: int, *, actor: User) -> Assignment:
    """Move a pending assignment within its machine's pending list (1 = next)."""
    assignment = get_assignment(db, assignment_id)
    machine = _lock_machine(db, assignment.machine_id)
    if assignment.status != "pending":
        raise _conflict(
            "INVALID_TRANSITION", "Solo se pueden reordenar asignaciones pendientes.",
            {"status": assignment.status},
        )
    pending = [
        a for a in machine_open_assignments(db, [machine.id]) if a.status == "pending"
    ]
    old_index = next(i for i, a in enumerate(pending) if a.id == assignment.id)
    pending.pop(old_index)
    new_index = min(position, len(pending) + 1) - 1
    pending.insert(new_index, assignment)
    for i, a in enumerate(pending, start=1):
        a.queue_position = i
    db.flush()
    if new_index != old_index:
        order = db.get(WorkOrder, assignment.order_id)
        assert order is not None
        _audit_order(
            db, order, "queue", actor,
            {"machine": machine.code, "queue_position": old_index + 1},
            {"machine": machine.code, "queue_position": new_index + 1},
        )
    db.commit()
    db.refresh(assignment)
    return assignment


# Production actions -----------------------------------------------------------------


def _check_plc_machine(assignment: Assignment, actor: Actor) -> None:
    if actor.machine is not None and actor.machine.id != assignment.machine_id:
        raise _conflict(
            "WRONG_MACHINE", "La asignación pertenece a otra máquina.",
            {"assignment_machine_id": assignment.machine_id},
        )


def _require(assignment: Assignment, allowed: tuple[str, ...], message: str) -> None:
    if assignment.status not in allowed:
        raise _conflict("INVALID_TRANSITION", message, {"status": assignment.status})


def _begin(db: Session, assignment_id: int, actor: Actor) -> tuple[Assignment, WorkOrder, Machine]:
    assignment = get_assignment(db, assignment_id)
    order = _lock_order(db, assignment.order_id)
    machine = _lock_machine(db, assignment.machine_id)
    db.refresh(assignment)  # re-read after taking the locks
    _check_plc_machine(assignment, actor)
    return assignment, order, machine


def _finish(
    db: Session, order: WorkOrder, assignment: Assignment, action: str, actor: Actor,
    before_status: str, liters: Decimal | None, commit: bool,
) -> Assignment:
    assignment.last_source = actor.source
    _event(db, assignment, action, actor, liters)
    db.flush()
    new_status = _sync_order_status(db, order, actor)
    after: dict[str, Any] = {"machine": assignment.machine.code, **_actor_info(actor)}
    if liters is not None:
        after["liters"] = str(_q(liters))
    if new_status != before_status:
        after["status"] = new_status
    _audit_order(
        db, order, action, actor,
        {"status": before_status} if new_status != before_status else None, after,
    )
    if commit:
        db.commit()
        db.refresh(assignment)
    return assignment


def start(db: Session, assignment_id: int, actor: Actor, *, commit: bool = True) -> Assignment:
    """pending -> running: only the machine's next ready assignment, only when
    the machine is free (BR-14) and the order is assigned (BR-20)."""
    assignment, order, machine = _begin(db, assignment_id, actor)
    _require(assignment, ("pending",), "Solo se puede iniciar una asignación pendiente.")
    queue = machine_queues(db, [machine])[machine.id]
    reason = start_blocked_reason(assignment, order.status, queue)
    if reason is not None:
        code = "ORDER_NOT_ASSIGNED" if order.status not in READY_STATUSES else "MACHINE_NOT_READY"
        raise _conflict(code, reason, {"order_status": order.status})
    before = order.status
    assignment.status = "running"
    assignment.started_at = utc_now()
    return _finish(db, order, assignment, "start", actor, before, None, commit)


def pause(db: Session, assignment_id: int, actor: Actor, *, commit: bool = True) -> Assignment:
    """running -> paused. Keeps liters and reservations (BR-23)."""
    assignment, order, _machine = _begin(db, assignment_id, actor)
    _require(assignment, ("running",), "Solo se puede pausar una asignación en proceso.")
    before = order.status
    assignment.status = "paused"
    return _finish(db, order, assignment, "pause", actor, before, None, commit)


def resume(db: Session, assignment_id: int, actor: Actor, *, commit: bool = True) -> Assignment:
    """paused -> running, on the same machine (BR-23, TODO(OPEN-20))."""
    assignment, order, machine = _begin(db, assignment_id, actor)
    _require(assignment, ("paused",), "Solo se puede reanudar una asignación en pausa.")
    if machine.in_maintenance:
        raise _conflict(
            "MACHINE_NOT_READY", f"La máquina {machine.code} está en mantenimiento.",
        )
    before = order.status
    assignment.status = "running"
    return _finish(db, order, assignment, "resume", actor, before, None, commit)


def complete(
    db: Session, assignment_id: int, actual_liters: Decimal, actor: Actor,
    *, commit: bool = True,
) -> Assignment:
    """running|paused -> completed with the actual liters; moves stock (BR-8).
    When it is the order's last assignment, the order becomes completed."""
    assignment, order, _machine = _begin(db, assignment_id, actor)
    _require(
        assignment, ("running", "paused"),
        "Solo se puede terminar una asignación en proceso o en pausa.",
    )
    liters = stock_service.normalize_quantity("product", Decimal(actual_liters))
    if liters < 0:
        raise _invalid("INVALID_QUANTITY", "Los litros reales no pueden ser negativos.")
    before = order.status
    assignment.status = "completed"
    assignment.actual_liters = liters
    assignment.completed_at = utc_now()
    db.flush()
    _move_stock_for_assignment(db, order, assignment, actor)
    return _finish(db, order, assignment, "complete", actor, before, liters, commit)


# Stock (BR-8, BR-9, BR-10) --------------------------------------------------------------


def _order_consumed(db: Session, order_id: int, item: ItemRef, types: tuple[str, ...]) -> Decimal:
    """Net quantity already taken out of stock for the order (positive)."""
    total = db.execute(
        select(func.coalesce(func.sum(StockMovement.quantity), 0)).where(
            StockMovement.order_id == order_id,
            StockMovement.type.in_(types),
            item.movement_filter(),
        )
    ).scalar_one()
    return -Decimal(total)


def _consume_reservation(db: Session, order: WorkOrder, item: ItemRef, quantity: Decimal) -> None:
    """Reduce the order's active reservation of `item` by `quantity`; the
    consumed part is kept as a `consumed` row, and the active row is marked
    `consumed` once exhausted (BR-8)."""
    if quantity <= 0:
        return
    row = (
        db.query(Reservation)
        .filter(
            Reservation.order_id == order.id,
            Reservation.status == "active",
            item.reservation_filter(),
        )
        .first()
    )
    if row is None:
        return
    if quantity >= Decimal(row.quantity):
        row.status = "consumed"
    else:
        row.quantity = Decimal(row.quantity) - quantity
        db.add(
            Reservation(
                order_id=order.id, site_id=row.site_id, product_id=row.product_id,
                packaging_item_id=row.packaging_item_id, quantity=quantity, status="consumed",
            )
        )
    db.flush()


def _move_stock_for_assignment(
    db: Session, order: WorkOrder, assignment: Assignment, actor: Actor
) -> None:
    """Finished product +A; each base product -(its liters x A / order liters),
    proportional [PROPOSED]. Base consumption is computed on the cumulative
    actual liters of the order's completed assignments and only the
    difference with what was already consumed is written, so rounding to 2
    decimals never loses liters across assignments."""
    a_liters = Decimal(assignment.actual_liters or 0)
    note = f"Orden {order.operation_number} — {assignment.machine.code}"
    if a_liters > 0:
        stock_service.apply_movement(
            db, site_id=order.site_id, item=ItemRef("product", order.finished_product_id),
            movement_type="production", quantity=a_liters, user=actor.user, note=note,
            order_id=order.id, assignment_id=assignment.id,
        )
    completed = [
        a for a in order_assignments(db, order.id, include_cancelled=False)
        if a.status == "completed"
    ]
    cumulative = actual_total(completed)
    ordered = Decimal(order.finished_liters)
    for row in order.base_products:
        item = ItemRef("product", row.product_id)
        target = _q(Decimal(row.liters) * cumulative / ordered)
        delta = target - _order_consumed(db, order.id, item, ("consumption",))
        if delta == 0:
            continue
        # BR-9: recorded even if on hand goes negative (raises an inventory alert).
        stock_service.apply_movement(
            db, site_id=order.site_id, item=item, movement_type="consumption",
            quantity=-delta, user=actor.user, note=note, order_id=order.id,
            assignment_id=assignment.id,
        )
        _consume_reservation(db, order, item, delta)


def packaging_effective_qty(row: Any) -> int:
    """Actual quantity if entered, else planned (BR-8)."""
    return int(row.actual_qty if row.actual_qty is not None else row.planned_qty)


def _complete_order(db: Session, order: WorkOrder, actor: Actor) -> None:
    """Order completed: packaging consumed per order, then every remaining
    active reservation released (BR-8, BR-10)."""
    note = f"Orden {order.operation_number} — material de empaque"
    for row in order.packaging:
        qty = packaging_effective_qty(row)
        if qty > 0:
            stock_service.apply_movement(
                db, site_id=order.site_id, item=ItemRef("packaging", row.packaging_item_id),
                movement_type="consumption", quantity=Decimal(-qty), user=actor.user,
                note=note, order_id=order.id,
            )
    reservation_service.release_for_order(db, order)


def correct_packaging(db: Session, order: WorkOrder, actor: User) -> list[dict[str, Any]]:
    """After completion (before closing), actual packaging changes write only
    the difference: more used -> `consumption`, less used -> `adjustment`
    back into stock. No commit. Returns the corrections for the audit."""
    corrections: list[dict[str, Any]] = []
    note = f"Corrección de material — orden {order.operation_number}"
    for row in order.packaging:
        item = ItemRef("packaging", row.packaging_item_id)
        consumed = _order_consumed(db, order.id, item, ("consumption", "adjustment"))
        delta = Decimal(packaging_effective_qty(row)) - consumed
        if delta == 0:
            continue
        stock_service.apply_movement(
            db, site_id=order.site_id, item=item,
            movement_type="consumption" if delta > 0 else "adjustment",
            quantity=-delta, user=actor, note=note, order_id=order.id,
        )
        corrections.append({"packaging_item_id": row.packaging_item_id, "delta": int(delta)})
    return corrections
