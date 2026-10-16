"""PLC event processor (phase 4).

Applies the rows the PLCs insert into `plc_events` through the same
assignment service used by the platform's production buttons (phase 3), with
`Actor.plc(machine)`, so stock, statuses and audit follow the same rules.

BR-13: unprocessed events are applied in `received_at` order (then id), each
in its own transaction. An event whose (machine, seq) was already seen is a
`duplicate` and is not applied. An event that is invalid for the
assignment's state is `rejected`; `reject_reason` is "CODE: detail", with
CODE one of NOT_ON_MACHINE, INVALID_TRANSITION, NOT_FIRST_IN_QUEUE,
BAD_PAYLOAD (or INTERNAL_ERROR for an unexpected bug, so one bad event never
blocks the machine's later events). Rejections are logged at warning level.

The background runner that calls `process_pending` lives in
`app/services/plc_listener.py`.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.timezone import utc_now
from app.models.assignments import Assignment
from app.models.catalogs import Machine
from app.models.plc import PlcEvent
from app.services import assignment_service
from app.services.assignment_service import Actor

logger = logging.getLogger(__name__)

# Events for these assignment statuses are always rejected.
_ENDED = frozenset({"completed", "cancelled"})
_NEEDS_LITERS = frozenset({"progress", "complete"})
BATCH_SIZE = 200


class Rejected(Exception):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


def _is_duplicate(db: Session, event: PlcEvent) -> bool:
    if event.seq is None:
        return False
    earlier = db.execute(
        select(PlcEvent.id).where(
            PlcEvent.machine_id == event.machine_id,
            PlcEvent.seq == event.seq,
            PlcEvent.id < event.id,
        ).limit(1)
    ).first()
    return earlier is not None


def _reject_code(exc: AppError) -> str:
    if exc.code == "WRONG_MACHINE":
        return "NOT_ON_MACHINE"
    if exc.code == "INVALID_QUANTITY":
        return "BAD_PAYLOAD"
    if (exc.details or {}).get("block") == "not_first":
        return "NOT_FIRST_IN_QUEUE"
    return "INVALID_TRANSITION"


def _apply(db: Session, event: PlcEvent, machine: Machine) -> None:
    """Apply one event (no commit). Raises Rejected or AppError."""
    if event.assignment_id is None:
        raise Rejected("BAD_PAYLOAD", "falta assignment_id")
    if event.event in _NEEDS_LITERS and event.liters is None:
        raise Rejected("BAD_PAYLOAD", f"el evento {event.event} requiere liters")
    assignment = db.get(Assignment, event.assignment_id)
    if assignment is None or assignment.machine_id != machine.id:
        raise Rejected(
            "NOT_ON_MACHINE",
            f"la asignación {event.assignment_id} no pertenece a la máquina {machine.code}",
        )
    if assignment.status in _ENDED:
        raise Rejected(
            "INVALID_TRANSITION", f"la asignación ya está {assignment.status}"
        )
    actor = Actor.plc(machine)
    liters = Decimal(event.liters) if event.liters is not None else Decimal(0)
    if event.event == "start":
        assignment_service.start(db, assignment.id, actor, commit=False)
    elif event.event == "progress":
        assignment_service.record_progress(db, assignment.id, liters, actor, commit=False)
    elif event.event == "pause":
        assignment_service.pause(db, assignment.id, actor, commit=False)
    elif event.event == "resume":
        assignment_service.resume(db, assignment.id, actor, commit=False)
    elif event.event == "complete":
        assignment_service.complete(db, assignment.id, liters, actor, commit=False)
    elif event.event == "error":
        assignment_service.record_error(
            db, assignment.id, event.error_code, event.message, actor, commit=False
        )
    else:  # the table's check constraint makes this unreachable
        raise Rejected("BAD_PAYLOAD", f"evento desconocido {event.event}")


def _mark(event: PlcEvent, result: str, reason: str | None = None) -> None:
    event.processed_at = utc_now()
    event.result = result
    event.reject_reason = reason


def process_event(db: Session, event_id: int) -> str:
    """Process one event in its own transaction; returns the result."""
    event = db.get(PlcEvent, event_id)
    if event is None or event.processed_at is not None:
        db.rollback()
        return "skipped"
    machine = db.get(Machine, event.machine_id)
    assert machine is not None  # FK + trigger
    if _is_duplicate(db, event):
        _mark(event, "duplicate")
        db.commit()
        return "duplicate"
    reason: str | None = None
    try:
        # An error event without an assignment is a machine-level error: kept
        # in plc_events (shown on the machine board), nothing else to apply.
        if not (event.event == "error" and event.assignment_id is None):
            _apply(db, event, machine)
        _mark(event, "applied")
        db.commit()
        return "applied"
    except Rejected as exc:
        reason = str(exc)
    except AppError as exc:
        reason = f"{_reject_code(exc)}: {exc.message}"
    except Exception:  # noqa: BLE001 - never block the machine's queue
        logger.exception("PLC event %s failed unexpectedly", event_id)
        reason = "INTERNAL_ERROR: error interno al aplicar el evento (ver el log del api)"
    db.rollback()
    event = db.get(PlcEvent, event_id)
    assert event is not None
    _mark(event, "rejected", reason)
    db.commit()
    logger.warning(
        "PLC event %s rejected (machine %s, assignment %s, %s): %s",
        event.id, machine.code, event.assignment_id, event.event, reason,
    )
    return "rejected"


def process_pending(session_factory: Callable[[], Session]) -> int:
    """Process every unprocessed event in received_at order. Returns how many
    events were processed."""
    count = 0
    while True:
        with session_factory() as db:
            ids = list(
                db.execute(
                    select(PlcEvent.id)
                    .where(PlcEvent.processed_at.is_(None))
                    .order_by(PlcEvent.received_at, PlcEvent.id)
                    .limit(BATCH_SIZE)
                ).scalars()
            )
            db.rollback()
            for event_id in ids:
                process_event(db, event_id)
                count += 1
        if len(ids) < BATCH_SIZE:
            return count
