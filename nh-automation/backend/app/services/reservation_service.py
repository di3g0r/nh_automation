"""Order reservations (FR-INV-5..9, BR-1..4, BR-10).

`reserve_for_order` is the only writer of active reservations. Within the
caller's transaction it:
1. locks the stock_levels rows of every base product at the order's site,
   always in stock-row id order, so two transactions touching the same
   products never deadlock (BR-3);
2. re-reads the active reservations (other orders only) after taking the
   locks, so a concurrent order that committed first is seen (BR-2);
3. blocks with INSUFFICIENT_STOCK if any base product is short, listing only
   the short products with on hand / reserved / available and the orders
   holding reservations;
4. computes packaging shortages as warnings (BR-4, never blocking);
5. releases the order's previous reservations and writes the new ones
   (per item kind, only for the parts that changed).

Base products without a stock row have 0 on hand, so they always fail the
check; no stock row is created here.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models.catalogs import PackagingItem, Product
from app.models.orders import Reservation, WorkOrder
from app.models.stock import StockLevel
from app.services import stock_service
from app.services.stock_service import ItemRef


def format_liters(value: Decimal) -> str:
    """`1,500.00 L`, the same format as the UI (overview §6)."""
    return f"{value:,.2f} L"


@dataclass(frozen=True)
class ProductNeed:
    product: Product
    liters: Decimal


@dataclass(frozen=True)
class PackagingNeed:
    item: PackagingItem
    quantity: int


def holders(
    db: Session, site_id: int, item: ItemRef, *, exclude_order_id: int | None = None
) -> list[tuple[WorkOrder, Decimal]]:
    """Orders holding active reservations of `item` at `site_id`, oldest first."""
    query = (
        db.query(WorkOrder, Reservation.quantity)
        .join(Reservation, Reservation.order_id == WorkOrder.id)
        .filter(
            Reservation.site_id == site_id,
            Reservation.status == "active",
            item.reservation_filter(),
        )
    )
    if exclude_order_id is not None:
        query = query.filter(WorkOrder.id != exclude_order_id)
    return [(o, Decimal(q)) for o, q in query.order_by(WorkOrder.id).all()]


def _lock_product_levels(
    db: Session, site_id: int, product_ids: Sequence[int]
) -> dict[int, Decimal]:
    """SELECT ... FOR UPDATE on the stock rows, ordered by id (BR-3)."""
    rows = db.execute(
        select(StockLevel)
        .where(StockLevel.site_id == site_id, StockLevel.product_id.in_(product_ids))
        .order_by(StockLevel.id)
        .with_for_update()
    ).scalars()
    return {row.product_id: Decimal(row.on_hand) for row in rows if row.product_id is not None}


def _shortage(
    db: Session, order_id: int | None, site_id: int, need: ProductNeed, on_hand: Decimal
) -> dict[str, Any] | None:
    item = ItemRef("product", need.product.id)
    reserved = stock_service.get_reserved(db, site_id, item, exclude_order_id=order_id)
    available = on_hand - reserved
    if available >= need.liters:
        return None
    holding = holders(db, site_id, item, exclude_order_id=order_id)
    return {
        "product_id": need.product.id,
        "code": need.product.code,
        "name": need.product.name,
        "required": str(need.liters),
        "on_hand": str(on_hand),
        "reserved": str(reserved),
        "available": str(available),
        "orders": [
            {"order_id": o.id, "operation_number": o.operation_number, "quantity": str(q)}
            for o, q in holding
        ],
    }


def _shortage_message(s: dict[str, Any]) -> str:
    msg = (
        f"Inventario insuficiente de {s['name']}: existencia "
        f"{format_liters(Decimal(s['on_hand']))}, reservado "
        f"{format_liters(Decimal(s['reserved']))}, disponible "
        f"{format_liters(Decimal(s['available']))}."
    )
    if s["orders"]:
        held = ", ".join(
            f"{o['operation_number']} ({format_liters(Decimal(o['quantity']))})"
            for o in s["orders"]
        )
        msg += f" Reservado por: {held}."
    return msg


def packaging_warnings(
    db: Session, order_id: int | None, site_id: int, needs: Sequence[PackagingNeed]
) -> list[dict[str, Any]]:
    """BR-4: planned packaging above what is available -> warning, not a block."""
    warnings: list[dict[str, Any]] = []
    for need in needs:
        avail = stock_service.get_available(
            db, ItemRef("packaging", need.item.id), site_id, exclude_order_id=order_id
        )
        if avail.available < need.quantity:
            warnings.append(
                {
                    "type": "packaging_shortage",
                    "packaging_item_id": need.item.id,
                    "code": need.item.code,
                    "description": need.item.description,
                    "planned": need.quantity,
                    "available": int(avail.available),
                }
            )
    return warnings


def reserve_for_order(
    db: Session,
    order: WorkOrder,
    products: Sequence[ProductNeed] | None,
    packaging: Sequence[PackagingNeed] | None,
) -> list[dict[str, Any]] | None:
    """Check, then replace the order's active reservations.

    `None` for `products` / `packaging` means "unchanged": those reservations
    are kept and not re-checked (an edit that only touches packaging must not
    fail because product stock moved since creation). Returns the packaging
    warnings when packaging was given, else None.

    The order must be flushed (it needs an id). Raises INSUFFICIENT_STOCK
    without writing anything if any base product is short; the caller's
    transaction is then rolled back.
    """
    if products is not None:
        on_hand = _lock_product_levels(db, order.site_id, [n.product.id for n in products])
        shortages = [
            s
            for n in products
            if (s := _shortage(
                db, order.id, order.site_id, n, on_hand.get(n.product.id, Decimal(0))
            ))
        ]
        if shortages:
            raise AppError(
                "INSUFFICIENT_STOCK",
                " ".join(_shortage_message(s) for s in shortages),
                409,
                {"items": shortages},
            )
        release_for_order(db, order, item_type="product")
        for n in products:
            db.add(
                Reservation(
                    order_id=order.id, site_id=order.site_id, product_id=n.product.id,
                    quantity=n.liters, status="active",
                )
            )

    warnings = None
    if packaging is not None:
        warnings = packaging_warnings(db, order.id, order.site_id, packaging)
        release_for_order(db, order, item_type="packaging")
        for p in packaging:
            db.add(
                Reservation(
                    order_id=order.id, site_id=order.site_id, packaging_item_id=p.item.id,
                    quantity=Decimal(p.quantity), status="active",
                )
            )
    db.flush()
    return warnings


def release_for_order(
    db: Session, order: WorkOrder, *, item_type: str | None = None
) -> int:
    """BR-10: mark the order's active reservations (optionally one item kind) released."""
    query = db.query(Reservation).filter(
        Reservation.order_id == order.id, Reservation.status == "active"
    )
    if item_type == "product":
        query = query.filter(Reservation.product_id.is_not(None))
    elif item_type == "packaging":
        query = query.filter(Reservation.packaging_item_id.is_not(None))
    rows = query.all()
    for r in rows:
        r.status = "released"
    db.flush()
    return len(rows)


def active_reservations(db: Session, order: WorkOrder) -> dict[tuple[str, int], Decimal]:
    """{("product"|"packaging", item_id): quantity} of the order's active reservations."""
    out: dict[tuple[str, int], Decimal] = {}
    for r in db.query(Reservation).filter(
        Reservation.order_id == order.id, Reservation.status == "active"
    ):
        key = ("product", r.product_id) if r.product_id else ("packaging", r.packaging_item_id)
        out[key] = Decimal(r.quantity)  # type: ignore[index]
    return out
