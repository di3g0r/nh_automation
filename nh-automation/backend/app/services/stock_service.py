"""Stock primitives shared by every phase (BR-1, BR-3, BR-5, BR-9).

- `apply_movement` is the ONLY way `stock_levels.on_hand` changes: it locks
  the stock_levels row (`SELECT ... FOR UPDATE`), applies the delta with an
  atomic SQL increment, and writes the `stock_movements` row in the same
  transaction. It never commits: callers compose it with their own writes
  (e.g. phase 3 completion) and commit once.
- `get_available` = on hand - active reservations (BR-1). Reservations arrive
  in phase 2; until then reserved is always 0.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models.catalogs import PackagingItem, Product
from app.models.stock import MOVEMENT_TYPES, StockLevel, StockMovement
from app.models.user import User

ItemType = Literal["product", "packaging"]
TWO_PLACES = Decimal("0.01")


@dataclass(frozen=True)
class ItemRef:
    item_type: ItemType
    item_id: int

    @property
    def column_values(self) -> dict[str, int | None]:
        if self.item_type == "product":
            return {"product_id": self.item_id, "packaging_item_id": None}
        return {"product_id": None, "packaging_item_id": self.item_id}

    def level_filter(self):  # type: ignore[no-untyped-def]
        if self.item_type == "product":
            return StockLevel.product_id == self.item_id
        return StockLevel.packaging_item_id == self.item_id

    def movement_filter(self):  # type: ignore[no-untyped-def]
        if self.item_type == "product":
            return StockMovement.product_id == self.item_id
        return StockMovement.packaging_item_id == self.item_id


@dataclass(frozen=True)
class Availability:
    on_hand: Decimal
    reserved: Decimal

    @property
    def available(self) -> Decimal:
        return self.on_hand - self.reserved


def item_model(item_type: ItemType) -> type[Product | PackagingItem]:
    return Product if item_type == "product" else PackagingItem


def normalize_quantity(item_type: ItemType, value: Decimal) -> Decimal:
    """Liters: max 2 decimals. Packaging: whole units only (data model §1)."""
    if item_type == "packaging":
        if value != value.to_integral_value():
            raise AppError(
                "INVALID_QUANTITY",
                "Los materiales de empaque se registran en unidades enteras.",
                422,
            )
        return value.quantize(Decimal("1"))
    if value != value.quantize(TWO_PLACES, rounding=ROUND_HALF_UP):
        raise AppError(
            "INVALID_QUANTITY", "Las cantidades en litros admiten máximo 2 decimales.", 422
        )
    return value.quantize(TWO_PLACES)


def _level_query(site_id: int, item: ItemRef):  # type: ignore[no-untyped-def]
    return select(StockLevel).where(StockLevel.site_id == site_id, item.level_filter())


def get_level(db: Session, site_id: int, item: ItemRef) -> StockLevel | None:
    return db.execute(_level_query(site_id, item)).scalar_one_or_none()


def get_on_hand(db: Session, site_id: int, item: ItemRef) -> Decimal:
    level = get_level(db, site_id, item)
    return Decimal(level.on_hand) if level else Decimal("0")


def get_reserved(db: Session, site_id: int, item: ItemRef) -> Decimal:
    # TODO(phase 2): sum of active reservations for this item and site (BR-1).
    return Decimal("0")


def get_available(db: Session, item: ItemRef, site_id: int) -> Availability:
    return Availability(
        on_hand=get_on_hand(db, site_id, item), reserved=get_reserved(db, site_id, item)
    )


def lock_level(db: Session, site_id: int, item: ItemRef) -> StockLevel:
    """Return the stock_levels row for (site, item), locked FOR UPDATE (BR-3).

    Creates it at 0 if missing. Two transactions racing to create the same row
    hit the unique constraint; the loser rolls back its savepoint and locks the
    winner's row instead.
    """
    level = db.execute(_level_query(site_id, item).with_for_update()).scalar_one_or_none()
    if level is not None:
        return level
    try:
        with db.begin_nested():
            level = StockLevel(site_id=site_id, on_hand=Decimal("0"), **item.column_values)
            db.add(level)
            db.flush()
    except IntegrityError:
        level = db.execute(_level_query(site_id, item).with_for_update()).scalar_one()
    return level


def apply_movement(
    db: Session,
    *,
    site_id: int,
    item: ItemRef,
    movement_type: str,
    quantity: Decimal,
    user: User | None,
    note: str | None = None,
    order_id: int | None = None,
    assignment_id: int | None = None,
) -> StockMovement:
    """Write one movement and update on hand by `quantity` (signed). No commit.

    Negative results are allowed (BR-9: consumption is recorded even if stock
    goes negative); they surface as alerts in inventory_service.
    """
    if movement_type not in MOVEMENT_TYPES:
        raise ValueError(f"Unknown movement type: {movement_type}")
    quantity = normalize_quantity(item.item_type, quantity)

    level = lock_level(db, site_id, item)
    # Atomic increment: correct even on engines that ignore FOR UPDATE.
    db.execute(
        update(StockLevel)
        .where(StockLevel.id == level.id)
        .values(on_hand=StockLevel.on_hand + quantity)
        .execution_options(synchronize_session=False)
    )
    db.expire(level, ["on_hand"])

    movement = StockMovement(
        site_id=site_id,
        type=movement_type,
        quantity=quantity,
        user_id=user.id if user else None,
        note=note,
        order_id=order_id,
        assignment_id=assignment_id,
        **item.column_values,
    )
    db.add(movement)
    db.flush()
    return movement


def has_movements(db: Session, site_id: int, item: ItemRef) -> bool:
    return (
        db.query(StockMovement.id)
        .filter(StockMovement.site_id == site_id, item.movement_filter())
        .first()
        is not None
    )
