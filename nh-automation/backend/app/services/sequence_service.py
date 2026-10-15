"""Order-number sequences (phase 1b; consumed by order creation in phase 2, BR-19).

The master admin (`sequences.manage`) may change the next number of each
sequence. Every change is audited. Lowering the number can make phase 2 hand
out a number that already exists; phase 2's unique operation_number rejects it.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.errors import not_found
from app.models.sequences import ORDER_TYPES, OrderSequence
from app.models.user import User
from app.services import audit_service

SEED_SEQUENCES = [("trabajo", "T"), ("retrabajo", "R")]


def list_sequences(db: Session) -> list[OrderSequence]:
    rows = db.query(OrderSequence).all()
    return sorted(rows, key=lambda r: ORDER_TYPES.index(r.order_type))


def get_sequence(db: Session, order_type: str, *, lock: bool = False) -> OrderSequence:
    query = db.query(OrderSequence).filter(OrderSequence.order_type == order_type)
    if lock:
        query = query.with_for_update()
    row = query.first()
    if row is None:
        raise not_found("Secuencia")
    return row


def set_next_number(
    db: Session, order_type: str, next_number: int, *, actor: User
) -> OrderSequence:
    row = get_sequence(db, order_type, lock=True)
    before = {"prefix": row.prefix, "next_number": row.next_number}
    if row.next_number != next_number:
        row.next_number = next_number
        db.flush()
        audit_service.record(
            db, user=actor, entity="order_sequence", entity_id=row.id, action="update",
            before=before, after={"prefix": row.prefix, "next_number": row.next_number},
        )
    db.commit()
    db.refresh(row)
    return row


def ensure_sequences(db: Session) -> None:
    """Idempotent seed (the phase-1b migration inserts the same rows). No commit."""
    for order_type, prefix in SEED_SEQUENCES:
        if db.query(OrderSequence).filter(OrderSequence.order_type == order_type).first() is None:
            db.add(OrderSequence(order_type=order_type, prefix=prefix, next_number=1))
    db.flush()
