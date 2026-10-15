"""Order sequence endpoints (phase 1b). Permission: sequences.manage (master admin)."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_permission
from app.core.permissions import Permission
from app.models.user import User
from app.schemas.sequences import OrderSequenceOut, OrderSequenceUpdate
from app.services import sequence_service

router = APIRouter(prefix="/order-sequences", tags=["sequences"])

_manage = require_permission(Permission.SEQUENCES_MANAGE)


@router.get("", response_model=list[OrderSequenceOut])
def list_sequences(
    db: Session = Depends(get_db), _actor: User = Depends(_manage)
) -> list[OrderSequenceOut]:
    return [OrderSequenceOut.model_validate(r) for r in sequence_service.list_sequences(db)]


@router.patch("/{order_type}", response_model=OrderSequenceOut)
def update_sequence(
    order_type: Literal["trabajo", "retrabajo"],
    payload: OrderSequenceUpdate,
    db: Session = Depends(get_db),
    actor: User = Depends(_manage),
) -> OrderSequenceOut:
    row = sequence_service.set_next_number(db, order_type, payload.next_number, actor=actor)
    return OrderSequenceOut.model_validate(row)
