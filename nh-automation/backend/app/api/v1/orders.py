"""Work order endpoints (phase 2).

View: orders.view. Create/edit/delete: orders.edit. Cancel: orders.cancel.
Comments: orders.comment. Phase-3 order actions (expiry, assignments,
traceability, closing) live in app/api/v1/production.py.
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_permission
from app.core.permissions import Permission
from app.models.user import User
from app.schemas.common import Page
from app.schemas.orders import (
    CancelIn,
    CommentIn,
    CommentOut,
    HistoryEntry,
    OrderCreate,
    OrderListItem,
    OrderOut,
    OrderStatus,
    OrderType,
    OrderUpdate,
    PrintData,
)
from app.services import order_service

router = APIRouter(prefix="/orders", tags=["orders"])

_view = require_permission(Permission.ORDERS_VIEW)
_edit = require_permission(Permission.ORDERS_EDIT)
_cancel = require_permission(Permission.ORDERS_CANCEL)
_comment = require_permission(Permission.ORDERS_COMMENT)

_STATUSES = set(OrderStatus.__args__)  # type: ignore[attr-defined]


@router.get("", response_model=Page[OrderListItem])
def list_orders(
    status: str | None = Query(None, description="One status or several, comma-separated"),
    order_type: OrderType | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    client_id: int | None = None,
    razon_social_id: int | None = None,
    product_id: int | None = None,
    site_id: int | None = None,
    search: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
    _actor: User = Depends(_view),
) -> Page[OrderListItem]:
    statuses = [s for s in (status or "").split(",") if s in _STATUSES] or None
    items, total = order_service.list_orders(
        db, statuses=statuses, order_type=order_type, date_from=date_from, date_to=date_to,
        client_id=client_id, razon_social_id=razon_social_id, product_id=product_id,
        site_id=site_id, search=search, page=page, page_size=page_size,
    )
    return Page[OrderListItem](items=items, total=total)


@router.post("", response_model=OrderOut, status_code=201)
def create_order(
    payload: OrderCreate, db: Session = Depends(get_db), actor: User = Depends(_edit)
) -> OrderOut:
    order = order_service.create_order(db, payload, actor=actor)
    return order_service.order_out(db, order)


@router.get("/{order_id}", response_model=OrderOut)
def get_order(
    order_id: int, db: Session = Depends(get_db), _actor: User = Depends(_view)
) -> OrderOut:
    return order_service.order_out(db, order_service.get_order(db, order_id))


@router.patch("/{order_id}", response_model=OrderOut)
def update_order(
    order_id: int,
    payload: OrderUpdate,
    db: Session = Depends(get_db),
    actor: User = Depends(_edit),
) -> OrderOut:
    order = order_service.update_order(db, order_id, payload, actor=actor)
    return order_service.order_out(db, order)


@router.delete("/{order_id}", status_code=204)
def delete_order(
    order_id: int, db: Session = Depends(get_db), actor: User = Depends(_edit)
) -> Response:
    order_service.delete_order(db, order_id, actor=actor)
    return Response(status_code=204)


@router.post("/{order_id}/cancel", response_model=OrderOut)
def cancel_order(
    order_id: int,
    payload: CancelIn,
    db: Session = Depends(get_db),
    actor: User = Depends(_cancel),
) -> OrderOut:
    order = order_service.cancel_order(db, order_id, payload.reason, actor=actor)
    return order_service.order_out(db, order)


@router.get("/{order_id}/comments", response_model=list[CommentOut])
def list_comments(
    order_id: int, db: Session = Depends(get_db), _actor: User = Depends(_view)
) -> list[CommentOut]:
    return order_service.list_comments(db, order_id)


@router.post("/{order_id}/comments", response_model=CommentOut, status_code=201)
def add_comment(
    order_id: int,
    payload: CommentIn,
    db: Session = Depends(get_db),
    actor: User = Depends(_comment),
) -> CommentOut:
    comment = order_service.add_comment(db, order_id, payload.text, actor=actor)
    return CommentOut(
        id=comment.id, user_id=actor.id, user_name=actor.full_name, text=comment.text,
        created_at=comment.created_at,
    )


@router.get("/{order_id}/history", response_model=list[HistoryEntry])
def get_history(
    order_id: int, db: Session = Depends(get_db), _actor: User = Depends(_view)
) -> list[HistoryEntry]:
    return order_service.history(db, order_id)


@router.get("/{order_id}/print-data", response_model=PrintData)
def get_print_data(
    order_id: int, db: Session = Depends(get_db), _actor: User = Depends(_view)
) -> PrintData:
    return order_service.print_data(db, order_id)
