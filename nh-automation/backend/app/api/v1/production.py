"""Phase 3 endpoints: Producción sections, expiry, machine assignments, queues,
production controls, traceability, closing and the machine board.

Permissions (overview §4): Producción lists and assignments/queues
orders.assign; expiry orders.expiry; start/pause/resume/complete
production.control; checklist/lots/materials orders.traceability; closing
orders.close; board and queues machines.board. Production actions from the
platform are recorded with source "manual" (the PLC writes them from phase 4).

This router is registered before the catalogs router so `/machines/board`
is not captured by `/machines/{item_id}`.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_permission
from app.core.permissions import Permission
from app.models.user import User
from app.schemas.orders import OrderOut
from app.schemas.production import (
    AssignmentOut,
    AssignmentsIn,
    ChecklistIn,
    CloseIn,
    CompleteIn,
    ExpiryIn,
    MachineBoardItem,
    MachineQueueOut,
    MaterialsIn,
    ProductionOrder,
    QueuePositionIn,
    TraceabilityIn,
)
from app.services import assignment_service, order_service, production_service
from app.services.assignment_service import Actor

router = APIRouter(tags=["production"])

_assign = require_permission(Permission.ORDERS_ASSIGN)
_expiry = require_permission(Permission.ORDERS_EXPIRY)
_control = require_permission(Permission.PRODUCTION_CONTROL)
_trace = require_permission(Permission.ORDERS_TRACEABILITY)
_close = require_permission(Permission.ORDERS_CLOSE)
_board = require_permission(Permission.MACHINES_BOARD)


def _order(db: Session, order_id: int) -> OrderOut:
    return order_service.order_out(db, order_service.get_order(db, order_id))


def _assignment(db: Session, assignment_id: int) -> AssignmentOut:
    row = assignment_service.get_assignment(db, assignment_id)
    return production_service.assignment_rows(db, [row])[0]


# Producción (FR-PM-1) -------------------------------------------------------------


@router.get("/production/to-assign", response_model=list[ProductionOrder])
def to_assign(db: Session = Depends(get_db), _a: User = Depends(_assign)) -> list[ProductionOrder]:
    return production_service.to_assign(db)


@router.get("/production/in-production", response_model=list[ProductionOrder])
def in_production(
    db: Session = Depends(get_db), _a: User = Depends(_assign)
) -> list[ProductionOrder]:
    return production_service.in_production(db)


@router.get("/production/to-close", response_model=list[ProductionOrder])
def to_close(db: Session = Depends(get_db), _a: User = Depends(_assign)) -> list[ProductionOrder]:
    return production_service.to_close(db)


# Expiry and assignments ----------------------------------------------------------------


@router.put("/orders/{order_id}/expiry", response_model=OrderOut)
def set_expiry(
    order_id: int, payload: ExpiryIn, db: Session = Depends(get_db),
    actor: User = Depends(_expiry),
) -> OrderOut:
    order_service.set_expiry(db, order_id, payload.expiry_date, actor=actor)
    return _order(db, order_id)


@router.put("/orders/{order_id}/assignments", response_model=OrderOut)
def set_assignments(
    order_id: int, payload: AssignmentsIn, db: Session = Depends(get_db),
    actor: User = Depends(_assign),
) -> OrderOut:
    assignment_service.set_assignments(db, order_id, payload.assignments, actor=actor)
    return _order(db, order_id)


@router.patch("/assignments/{assignment_id}/queue-position", response_model=AssignmentOut)
def reorder(
    assignment_id: int, payload: QueuePositionIn, db: Session = Depends(get_db),
    actor: User = Depends(_assign),
) -> AssignmentOut:
    assignment_service.reorder(db, assignment_id, payload.queue_position, actor=actor)
    return _assignment(db, assignment_id)


# Production controls (manual fallback to the PLC) -----------------------------------------


@router.post("/assignments/{assignment_id}/start", response_model=AssignmentOut)
def start(
    assignment_id: int, db: Session = Depends(get_db), actor: User = Depends(_control)
) -> AssignmentOut:
    assignment_service.start(db, assignment_id, Actor.manual(actor))
    return _assignment(db, assignment_id)


@router.post("/assignments/{assignment_id}/pause", response_model=AssignmentOut)
def pause(
    assignment_id: int, db: Session = Depends(get_db), actor: User = Depends(_control)
) -> AssignmentOut:
    assignment_service.pause(db, assignment_id, Actor.manual(actor))
    return _assignment(db, assignment_id)


@router.post("/assignments/{assignment_id}/resume", response_model=AssignmentOut)
def resume(
    assignment_id: int, db: Session = Depends(get_db), actor: User = Depends(_control)
) -> AssignmentOut:
    assignment_service.resume(db, assignment_id, Actor.manual(actor))
    return _assignment(db, assignment_id)


@router.post("/assignments/{assignment_id}/complete", response_model=AssignmentOut)
def complete(
    assignment_id: int, payload: CompleteIn, db: Session = Depends(get_db),
    actor: User = Depends(_control),
) -> AssignmentOut:
    assignment_service.complete(db, assignment_id, payload.actual_liters, Actor.manual(actor))
    return _assignment(db, assignment_id)


# Traceability and closing ---------------------------------------------------------------


@router.patch("/orders/{order_id}/checklist", response_model=OrderOut)
def update_checklist(
    order_id: int, payload: ChecklistIn, db: Session = Depends(get_db),
    actor: User = Depends(_trace),
) -> OrderOut:
    order_service.update_checklist(db, order_id, payload, actor=actor)
    return _order(db, order_id)


@router.patch("/orders/{order_id}/traceability", response_model=OrderOut)
def update_traceability(
    order_id: int, payload: TraceabilityIn, db: Session = Depends(get_db),
    actor: User = Depends(_trace),
) -> OrderOut:
    order_service.update_traceability(db, order_id, payload, actor=actor)
    return _order(db, order_id)


@router.patch("/orders/{order_id}/materials", response_model=OrderOut)
def update_materials(
    order_id: int, payload: MaterialsIn, db: Session = Depends(get_db),
    actor: User = Depends(_trace),
) -> OrderOut:
    order_service.update_materials(db, order_id, payload, actor=actor)
    return _order(db, order_id)


@router.post("/orders/{order_id}/close", response_model=OrderOut)
def close_order(
    order_id: int, payload: CloseIn, db: Session = Depends(get_db),
    actor: User = Depends(_close),
) -> OrderOut:
    order_service.close_order(db, order_id, payload.note, actor=actor)
    return _order(db, order_id)


# Machines (FR-MCH-1, FR-ASG-3) ---------------------------------------------------------------


@router.get("/machines/board", response_model=list[MachineBoardItem])
def machine_board(
    db: Session = Depends(get_db), _a: User = Depends(_board)
) -> list[MachineBoardItem]:
    return production_service.board(db)


@router.get("/machines/{machine_id}/queue", response_model=MachineQueueOut)
def machine_queue(
    machine_id: int, db: Session = Depends(get_db), _a: User = Depends(_board)
) -> MachineQueueOut:
    return production_service.machine_queue(db, machine_id)
