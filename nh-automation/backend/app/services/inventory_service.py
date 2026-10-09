"""Inventory screens and manual stock moves (FR-INV-1..4, FR-INV-10/11).

Receipts and adjustments go through stock_service.apply_movement (BR-5) and
are audited (BR-18).
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import cast

from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.timezone import to_utc
from app.models.catalogs import PackagingItem, Product, Site
from app.models.stock import StockLevel, StockMovement
from app.models.user import User
from app.schemas.inventory import (
    AdjustmentIn,
    AlertItem,
    AlertsOut,
    InventoryRow,
    MovementOut,
    ReceiptIn,
)
from app.services import audit_service, stock_service
from app.services.catalog_service import get, require_active
from app.services.stock_service import ItemRef, ItemType

_ITEM_LABEL = {"product": "El producto", "packaging": "El material de empaque"}


def _item_name(item: Product | PackagingItem) -> str:
    return item.name if isinstance(item, Product) else item.description


def _reserved_map(
    db: Session, item_type: ItemType, site_ids: list[int]
) -> dict[tuple[int, int], Decimal]:
    # TODO(phase 2): aggregate active reservations per (site_id, item_id) (BR-1).
    return {}


def _level_map(
    db: Session, item_type: ItemType, site_ids: list[int]
) -> dict[tuple[int, int], Decimal]:
    item_col = StockLevel.product_id if item_type == "product" else StockLevel.packaging_item_id
    rows = (
        db.query(StockLevel.site_id, item_col, StockLevel.on_hand)
        .filter(StockLevel.site_id.in_(site_ids), item_col.is_not(None))
        .all()
    )
    return {(site_id, item_id): Decimal(on_hand) for site_id, item_id, on_hand in rows}


def list_inventory(
    db: Session,
    *,
    item_type: ItemType,
    site_id: int | None = None,
    category: str | None = None,
    search: str | None = None,
    low_stock: bool = False,
    negative: bool = False,
    include_inactive: bool = False,
    page: int = 1,
    page_size: int = 50,
) -> tuple[list[InventoryRow], int]:
    site_query = db.query(Site)
    if site_id is not None:
        site_query = site_query.filter(Site.id == site_id)
    else:
        site_query = site_query.filter(Site.is_active.is_(True))
    sites = site_query.order_by(Site.name).all()

    model = stock_service.item_model(item_type)
    item_query = db.query(model)
    if not include_inactive:
        item_query = item_query.filter(model.is_active.is_(True))
    if search:
        like = f"%{search.strip()}%"
        name_col = Product.name if item_type == "product" else PackagingItem.description
        item_query = item_query.filter(model.code.ilike(like) | name_col.ilike(like))
    if category and item_type == "packaging":
        item_query = item_query.filter(PackagingItem.category == category)
    items = cast(list[Product | PackagingItem], item_query.order_by(model.code).all())

    site_ids = [s.id for s in sites]
    levels = _level_map(db, item_type, site_ids)
    reserved = _reserved_map(db, item_type, site_ids)

    rows: list[InventoryRow] = []
    for item in items:
        threshold = item.low_stock_threshold if isinstance(item, PackagingItem) else None
        for site in sites:
            on_hand = levels.get((site.id, item.id), Decimal("0"))
            res = reserved.get((site.id, item.id), Decimal("0"))
            available = on_hand - res
            row = InventoryRow(
                item_type=item_type,
                item_id=item.id,
                code=item.code,
                name=_item_name(item),
                category=item.category if isinstance(item, PackagingItem) else None,
                is_active=item.is_active,
                site_id=site.id,
                site_name=site.name,
                on_hand=on_hand,
                reserved=res,
                available=available,
                low_stock_threshold=threshold,
                low_stock=_is_low(item, available),
                negative=on_hand < 0,
            )
            if low_stock and not row.low_stock:
                continue
            if negative and not row.negative:
                continue
            rows.append(row)

    total = len(rows)
    start = (page - 1) * page_size
    return rows[start : start + page_size], total


def _is_low(item: Product | PackagingItem, available: Decimal) -> bool:
    """FR-INV-10: packaging available strictly below its threshold."""
    return (
        isinstance(item, PackagingItem)
        and item.is_active
        and available < Decimal(item.low_stock_threshold)
    )


# Receipts / adjustments ------------------------------------------------------


def _load_targets(
    db: Session, item: ItemRef, site_id: int
) -> tuple[Product | PackagingItem, Site]:
    obj = cast(
        Product | PackagingItem, get(db, stock_service.item_model(item.item_type), item.item_id)
    )
    site = get(db, Site, site_id)
    require_active(obj, _ITEM_LABEL[item.item_type])
    require_active(site, "El sitio")
    return obj, site


def _movement_audit(movement: StockMovement, on_hand_before: Decimal, on_hand_after: Decimal):  # type: ignore[no-untyped-def]
    return (
        {"on_hand": str(on_hand_before)},
        {
            "on_hand": str(on_hand_after),
            "movement_id": movement.id,
            "type": movement.type,
            "site_id": movement.site_id,
            "product_id": movement.product_id,
            "packaging_item_id": movement.packaging_item_id,
            "quantity": str(movement.quantity),
            "note": movement.note,
        },
    )


def create_receipt(db: Session, data: ReceiptIn, *, actor: User) -> StockMovement:
    item = ItemRef(data.item_type, data.item_id)
    _load_targets(db, item, data.site_id)

    before = stock_service.lock_level(db, data.site_id, item).on_hand
    movement = stock_service.apply_movement(
        db, site_id=data.site_id, item=item, movement_type="receipt",
        quantity=data.quantity, user=actor, note=data.note or None,
    )
    after = stock_service.get_on_hand(db, data.site_id, item)
    b, a = _movement_audit(movement, Decimal(before), after)
    audit_service.record(
        db, user=actor, entity="stock", entity_id=movement.id, action="receipt",
        before=b, after=a,
    )
    db.commit()
    db.refresh(movement)
    return movement


def create_adjustment(db: Session, data: AdjustmentIn, *, actor: User) -> StockMovement:
    """FR-INV-3: user enters the counted quantity; the system computes the delta."""
    item = ItemRef(data.item_type, data.item_id)
    _load_targets(db, item, data.site_id)
    counted = stock_service.normalize_quantity(item.item_type, data.counted_quantity)

    level = stock_service.lock_level(db, data.site_id, item)  # locked: delta is stable
    before = Decimal(level.on_hand)
    delta = counted - before
    if delta == 0:
        raise AppError(
            "ADJUSTMENT_NO_CHANGE",
            "La cantidad contada es igual a la existencia actual; no hay nada que ajustar.",
            422,
        )
    movement = stock_service.apply_movement(
        db, site_id=data.site_id, item=item, movement_type="adjustment",
        quantity=delta, user=actor, note=data.reason,
    )
    b, a = _movement_audit(movement, before, counted)
    audit_service.record(
        db, user=actor, entity="stock", entity_id=movement.id, action="adjustment",
        before=b, after=a,
    )
    db.commit()
    db.refresh(movement)
    return movement


# Movements list --------------------------------------------------------------


def _local_day_start_utc(d: date) -> datetime:
    return to_utc(datetime.combine(d, time.min))


def _movements_query(db: Session):  # type: ignore[no-untyped-def]
    return (
        db.query(StockMovement, Site, Product, PackagingItem, User)
        .join(Site, Site.id == StockMovement.site_id)
        .outerjoin(Product, Product.id == StockMovement.product_id)
        .outerjoin(PackagingItem, PackagingItem.id == StockMovement.packaging_item_id)
        .outerjoin(User, User.id == StockMovement.user_id)
    )


def list_movements(
    db: Session,
    *,
    item_type: ItemType | None = None,
    item_id: int | None = None,
    site_id: int | None = None,
    movement_type: str | None = None,
    user_id: int | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    page: int = 1,
    page_size: int = 50,
) -> tuple[list[MovementOut], int]:
    query = _movements_query(db)
    if item_type == "product":
        query = query.filter(StockMovement.product_id.is_not(None))
        if item_id is not None:
            query = query.filter(StockMovement.product_id == item_id)
    elif item_type == "packaging":
        query = query.filter(StockMovement.packaging_item_id.is_not(None))
        if item_id is not None:
            query = query.filter(StockMovement.packaging_item_id == item_id)
    if site_id is not None:
        query = query.filter(StockMovement.site_id == site_id)
    if movement_type is not None:
        query = query.filter(StockMovement.type == movement_type)
    if user_id is not None:
        query = query.filter(StockMovement.user_id == user_id)
    # Date filters are local calendar days (NFR-7a), inclusive on both ends.
    if date_from is not None:
        query = query.filter(StockMovement.created_at >= _local_day_start_utc(date_from))
    if date_to is not None:
        query = query.filter(
            StockMovement.created_at < _local_day_start_utc(date_to + timedelta(days=1))
        )

    total = query.count()
    rows = (
        query.order_by(StockMovement.created_at.desc(), StockMovement.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return [_movement_out(*r) for r in rows], total


def _movement_out(
    m: StockMovement,
    site: Site,
    product: Product | None,
    packaging: PackagingItem | None,
    user: User | None,
) -> MovementOut:
    item: Product | PackagingItem = product if product is not None else packaging  # type: ignore[assignment]
    return MovementOut(
        id=m.id,
        created_at=m.created_at,
        type=m.type,
        item_type="product" if product is not None else "packaging",
        item_id=item.id,
        item_code=item.code,
        item_name=_item_name(item),
        site_id=site.id,
        site_name=site.name,
        quantity=m.quantity,
        order_id=m.order_id,
        assignment_id=m.assignment_id,
        user_id=m.user_id,
        user_name=user.full_name if user else None,
        note=m.note,
    )


def movement_out(db: Session, movement: StockMovement) -> MovementOut:
    row = _movements_query(db).filter(StockMovement.id == movement.id).one()
    return _movement_out(*row)


def list_movement_users(db: Session) -> list[User]:
    """Users who have recorded at least one movement (for the movements filter)."""
    ids = db.query(StockMovement.user_id).filter(StockMovement.user_id.is_not(None)).distinct()
    return db.query(User).filter(User.id.in_(ids)).order_by(User.full_name).all()


# Alerts ----------------------------------------------------------------------


def get_alerts(db: Session) -> AlertsOut:
    """FR-INV-10/11: low stock (active packaging, available < threshold, active
    sites) and negative on hand (any item, any site)."""
    low_rows, _ = list_inventory(
        db, item_type="packaging", low_stock=True, page_size=100_000
    )
    low = [
        AlertItem(
            kind="low_stock", item_type="packaging", item_id=r.item_id, code=r.code,
            name=r.name, site_id=r.site_id, site_name=r.site_name, on_hand=r.on_hand,
            available=r.available, low_stock_threshold=r.low_stock_threshold,
        )
        for r in low_rows
    ]

    negative: list[AlertItem] = []
    neg_levels = (
        db.query(StockLevel, Site, Product, PackagingItem)
        .join(Site, Site.id == StockLevel.site_id)
        .outerjoin(Product, Product.id == StockLevel.product_id)
        .outerjoin(PackagingItem, PackagingItem.id == StockLevel.packaging_item_id)
        .filter(StockLevel.on_hand < 0)
        .all()
    )
    for level, site, product, packaging in neg_levels:
        item: Product | PackagingItem = product if product is not None else packaging  # type: ignore[assignment]
        item_type: ItemType = "product" if product is not None else "packaging"
        ref = ItemRef(item_type, item.id)
        on_hand = Decimal(level.on_hand)
        negative.append(
            AlertItem(
                kind="negative_stock", item_type=item_type, item_id=item.id, code=item.code,
                name=_item_name(item), site_id=site.id, site_name=site.name, on_hand=on_hand,
                available=on_hand - stock_service.get_reserved(db, site.id, ref),
                low_stock_threshold=(
                    item.low_stock_threshold if isinstance(item, PackagingItem) else None
                ),
            )
        )
    negative.sort(key=lambda a: (a.item_type, a.code, a.site_name))

    return AlertsOut(low_stock=low, negative_stock=negative, count=len(low) + len(negative))
