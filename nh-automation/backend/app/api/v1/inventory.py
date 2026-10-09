"""Inventory endpoints (FR-INV). View: inventory.view. Receipts/adjustments: inventory.move."""

from __future__ import annotations

from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_permission
from app.core.permissions import Permission
from app.models.catalogs import Site
from app.models.user import User
from app.schemas.common import Page
from app.schemas.inventory import (
    AdjustmentIn,
    AlertsOut,
    Availability,
    InventoryRow,
    ItemType,
    MovementOut,
    MovementUser,
    ReceiptIn,
)
from app.services import catalog_service, inventory_service, stock_service

router = APIRouter(prefix="/inventory", tags=["inventory"])

_view = require_permission(Permission.INVENTORY_VIEW)
_move = require_permission(Permission.INVENTORY_MOVE)

MovementType = Literal["receipt", "adjustment", "consumption", "production"]


@router.get("", response_model=Page[InventoryRow])
def list_inventory(
    item_type: ItemType = "product",
    site_id: int | None = None,
    category: str | None = None,
    search: str | None = None,
    low_stock: bool = False,
    negative: bool = False,
    include_inactive: bool = False,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
    _actor: User = Depends(_view),
) -> Page[InventoryRow]:
    rows, total = inventory_service.list_inventory(
        db, item_type=item_type, site_id=site_id, category=category, search=search,
        low_stock=low_stock, negative=negative, include_inactive=include_inactive,
        page=page, page_size=page_size,
    )
    return Page[InventoryRow](items=rows, total=total)


@router.get("/movements", response_model=Page[MovementOut])
def list_movements(
    item_type: ItemType | None = None,
    item_id: int | None = None,
    site_id: int | None = None,
    type: MovementType | None = None,
    user_id: int | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
    _actor: User = Depends(_view),
) -> Page[MovementOut]:
    rows, total = inventory_service.list_movements(
        db, item_type=item_type, item_id=item_id, site_id=site_id, movement_type=type,
        user_id=user_id, date_from=date_from, date_to=date_to, page=page, page_size=page_size,
    )
    return Page[MovementOut](items=rows, total=total)


@router.get("/movement-users", response_model=list[MovementUser])
def list_movement_users(
    db: Session = Depends(get_db), _actor: User = Depends(_view)
) -> list[MovementUser]:
    return [
        MovementUser(id=u.id, full_name=u.full_name)
        for u in inventory_service.list_movement_users(db)
    ]


@router.post("/receipts", response_model=MovementOut, status_code=201)
def create_receipt(
    payload: ReceiptIn, db: Session = Depends(get_db), actor: User = Depends(_move)
) -> MovementOut:
    movement = inventory_service.create_receipt(db, payload, actor=actor)
    return inventory_service.movement_out(db, movement)


@router.post("/adjustments", response_model=MovementOut, status_code=201)
def create_adjustment(
    payload: AdjustmentIn, db: Session = Depends(get_db), actor: User = Depends(_move)
) -> MovementOut:
    movement = inventory_service.create_adjustment(db, payload, actor=actor)
    return inventory_service.movement_out(db, movement)


@router.get("/availability", response_model=Availability)
def get_availability(
    item_type: ItemType,
    item_id: int,
    site_id: int,
    db: Session = Depends(get_db),
    _actor: User = Depends(_view),
) -> Availability:
    catalog_service.get(db, stock_service.item_model(item_type), item_id)
    catalog_service.get(db, Site, site_id)
    a = stock_service.get_available(db, stock_service.ItemRef(item_type, item_id), site_id)
    return Availability(
        item_type=item_type, item_id=item_id, site_id=site_id,
        on_hand=a.on_hand, reserved=a.reserved, available=a.available,
    )


@router.get("/alerts", response_model=AlertsOut)
def get_alerts(db: Session = Depends(get_db), _actor: User = Depends(_view)) -> AlertsOut:
    return inventory_service.get_alerts(db)
