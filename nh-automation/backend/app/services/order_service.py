"""Work orders: create, edit, delete, cancel, comments, history, list and
print data (phase 2); expiry, traceability, materials and closing (phase 3).

Business rules implemented here (data model §4): BR-2/3/4/10 through
reservation_service, BR-6, BR-11 (closing), BR-16 (editing, also in Asignada),
BR-17 (delete/cancel), BR-18 (audit), BR-19 (numbering), BR-20 (expiry),
BR-21 (type / rework kinds), BR-22 (razón social), BR-24 (traceability).
Machine assignments and production actions live in assignment_service.
Every public write runs in one transaction and commits once at the end; any
AppError leaves the transaction uncommitted (nothing is saved, no number is
consumed).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import exists, or_, select
from sqlalchemy.orm import Session

from app.core.errors import AppError, not_found
from app.core.timezone import local_today, utc_now
from app.models.audit_log import AuditLog
from app.models.catalogs import Client, PackagingItem, Product, RazonSocial, Site
from app.models.orders import (
    CHECKLIST_ITEMS,
    OrderBaseProduct,
    OrderChecklistItem,
    OrderComment,
    OrderPackaging,
    WorkOrder,
)
from app.models.user import User
from app.schemas.orders import (
    BaseProductIn,
    BaseProductOut,
    ChecklistOut,
    CommentOut,
    HistoryEntry,
    OrderCreate,
    OrderListItem,
    OrderOut,
    OrderUpdate,
    PackagingIn,
    PackagingOut,
    PrintData,
    Signature,
)
from app.schemas.production import (
    ChecklistIn,
    MaterialsIn,
    MissingForClose,
    TraceabilityIn,
)
from app.services import (
    assignment_service,
    audit_service,
    catalog_service,
    production_service,
    reservation_service,
    sequence_service,
)
from app.services.reservation_service import PackagingNeed, ProductNeed

# BR-16: editable while nothing has started. Changing base products, liters or
# the finished product of an assigned order deletes its assignments.
EDITABLE_STATUSES = frozenset({"created", "assigned"})
EXPIRY_STATUSES = frozenset({"created", "assigned"})  # BR-20: until production starts
# BR-24: lots, checklist and actual materials are editable until the order is
# closed (closed orders are read-only except comments, BR-11).
TRACEABILITY_STATUSES = frozenset(
    {"created", "assigned", "in_progress", "paused", "completed"}
)
CANCELLABLE_STATUSES = frozenset({"created", "assigned"})  # BR-17
DELETABLE_STATUSES = frozenset({"created"})  # BR-17
RELATED_ORDER_STATUSES = ("completed", "closed")  # BR-21

AUDIT_ENTITY = "work_order"


def _invalid(code: str, message: str, details: dict[str, Any] | None = None) -> AppError:
    return AppError(code, message, 422, details)


# Loading and validation ----------------------------------------------------------


def get_order(db: Session, order_id: int, *, lock: bool = False) -> WorkOrder:
    query = db.query(WorkOrder).filter(WorkOrder.id == order_id)
    if lock:
        query = query.with_for_update()
    order = query.first()
    if order is None:
        raise not_found("Orden")
    return order


def _load_base_products(
    db: Session, items: list[BaseProductIn], keep_ids: set[int]
) -> list[ProductNeed]:
    """Products must exist, appear once, and have a razón social (BR-22).
    Products not already on the order must be active (FR-CAT-6)."""
    needs: list[ProductNeed] = []
    seen: set[int] = set()
    for item in items:
        product = catalog_service.get(db, Product, item.product_id)
        if product.id in seen:
            raise _invalid(
                "DUPLICATE_BASE_PRODUCT",
                f"El producto base {product.code} aparece más de una vez.",
                {"product_id": product.id},
            )
        seen.add(product.id)
        if product.id not in keep_ids:
            catalog_service.require_active(product, f"El producto {product.code}")
        if product.razon_social_id is None:
            raise _invalid(
                "PRODUCT_WITHOUT_RAZON_SOCIAL",
                f"El producto {product.code} no tiene razón social asignada y no puede "
                "usarse en una orden. Asígnela en Catálogos → Productos.",
                {"product_id": product.id},
            )
        needs.append(ProductNeed(product=product, liters=item.liters))
    return needs


def _load_packaging(
    db: Session, items: list[PackagingIn], keep_ids: set[int]
) -> list[PackagingNeed]:
    needs: list[PackagingNeed] = []
    seen: set[int] = set()
    for item in items:
        pkg = catalog_service.get(db, PackagingItem, item.packaging_item_id)
        if pkg.id in seen:
            raise _invalid(
                "DUPLICATE_PACKAGING",
                f"El material {pkg.code} aparece más de una vez.",
                {"packaging_item_id": pkg.id},
            )
        seen.add(pkg.id)
        if pkg.id not in keep_ids:
            catalog_service.require_active(pkg, f"El material {pkg.code}")
        needs.append(PackagingNeed(item=pkg, quantity=item.planned_qty))
    return needs


def _razon_social_options(needs: list[ProductNeed]) -> dict[int, RazonSocial]:
    return {
        n.product.razon_social_id: n.product.razon_social  # type: ignore[misc]
        for n in needs
        if n.product.razon_social is not None
    }


def _resolve_razon_social(
    needs: list[ProductNeed], requested_id: int | None
) -> RazonSocial:
    """BR-22: automatic when all base products share one; otherwise the user
    chooses among the base products' razones sociales."""
    options = _razon_social_options(needs)
    if requested_id is None:
        if len(options) == 1:
            return next(iter(options.values()))
        raise _invalid(
            "RAZON_SOCIAL_REQUIRED",
            "Los productos base pertenecen a distintas razones sociales; elija una.",
            {"options": [{"id": rs.id, "code": rs.code, "name": rs.name}
                         for rs in options.values()]},
        )
    if requested_id not in options:
        raise _invalid(
            "RAZON_SOCIAL_NOT_ALLOWED",
            "La razón social debe ser una de las de los productos base.",
            {"options": [{"id": rs.id, "code": rs.code, "name": rs.name}
                         for rs in options.values()]},
        )
    return options[requested_id]


def _load_related_order(db: Session, related_id: int | None, self_id: int | None) -> WorkOrder:
    """BR-21: a Retrabajo de orden anterior needs a completed or closed order."""
    if related_id is None:
        raise _invalid(
            "RELATED_ORDER_REQUIRED", "Seleccione la orden anterior que se va a retrabajar."
        )
    related = db.get(WorkOrder, related_id)
    if related is None or related.id == self_id:
        raise not_found("Orden relacionada")
    if related.status not in RELATED_ORDER_STATUSES:
        raise _invalid(
            "RELATED_ORDER_INVALID",
            f"La orden {related.operation_number} no está completada ni cerrada.",
            {"related_order_id": related.id, "status": related.status},
        )
    return related


def _resolve_client(
    db: Session, client_id: int | None, related: WorkOrder | None, *, check_active: bool
) -> Client:
    if client_id is None and related is not None:
        client_id = related.client_id  # defaults to the related order's client
    if client_id is None:
        raise _invalid("CLIENT_REQUIRED", "El cliente es obligatorio.")
    client = catalog_service.get(db, Client, client_id)
    if check_active:
        catalog_service.require_active(client, "El cliente")
    return client


def _load_site(db: Session, site_id: int | None, *, check_active: bool) -> Site:
    if site_id is None:
        site = catalog_service.get_default_site(db)
        if site is None:
            raise _invalid("SITE_REQUIRED", "No hay un sitio por defecto configurado.")
    else:
        site = catalog_service.get(db, Site, site_id)
    if check_active:
        catalog_service.require_active(site, "El sitio")
    return site


@dataclass
class _Rework:
    rework_kind: str | None
    related: WorkOrder | None
    client: Client | None


def _resolve_rework(
    db: Session,
    *,
    order_type: str,
    rework_kind: str | None,
    related_id: int | None,
    client_id: int | None,
    self_id: int | None,
    client_changed: bool,
) -> _Rework:
    """BR-21. Fields that do not apply to the type/kind are normalized to null."""
    if order_type == "trabajo":
        client = _resolve_client(db, client_id, None, check_active=client_changed)
        return _Rework(None, None, client)
    if rework_kind is None:
        raise _invalid("REWORK_KIND_REQUIRED", "Seleccione el tipo de retrabajo.")
    if rework_kind == "own_stock":
        return _Rework("own_stock", None, None)  # no client, no related order
    related = _load_related_order(db, related_id, self_id)
    client = _resolve_client(db, client_id, related, check_active=client_changed)
    return _Rework("previous_order", related, client)


def _copy_expiry(order: WorkOrder, related: WorkOrder, actor: User) -> None:
    """BR-20: Retrabajo de orden anterior keeps the related order's expiry (locked)."""
    order.expiry_date = related.expiry_date
    order.expiry_set_by = actor.id
    order.expiry_set_at = utc_now()


def expiry_locked(order: WorkOrder) -> bool:
    """BR-20: copied (previous order) or already entered once (own stock).
    Trabajo stays editable until production starts (phase 3)."""
    if order.rework_kind == "previous_order":
        return True
    return order.rework_kind == "own_stock" and order.expiry_date is not None


# Snapshots ----------------------------------------------------------------------


def _set_finished(order: WorkOrder, product: Product) -> None:
    """FR-ORD-1: finished product snapshot."""
    order.finished_product_id = product.id
    order.finished_code = product.code
    order.finished_name = product.name
    order.finished_provider = product.provider
    order.finished_presentation = product.presentation


def _new_base_row(need: ProductNeed, position: int) -> OrderBaseProduct:
    p = need.product
    return OrderBaseProduct(
        position=position, product_id=p.id, code=p.code, name=p.name, provider=p.provider,
        presentation=p.presentation,
        razon_social_code=p.razon_social.code if p.razon_social else "",
        liters=need.liters,
    )


def _sync_base_rows(order: WorkOrder, needs: list[ProductNeed]) -> None:
    """Rows for products already on the order keep their snapshot; new ones
    are snapshotted now (FR-ORD-1)."""
    existing = {row.product_id: row for row in order.base_products}
    wanted = {n.product.id for n in needs}
    for old in list(order.base_products):
        if old.product_id not in wanted:
            order.base_products.remove(old)
    for position, need in enumerate(needs, start=1):
        row = existing.get(need.product.id)
        if row is None:
            order.base_products.append(_new_base_row(need, position))
        else:
            row.position = position
            row.liters = need.liters


def _sync_packaging_rows(order: WorkOrder, needs: list[PackagingNeed]) -> None:
    existing = {row.packaging_item_id: row for row in order.packaging}
    wanted = {n.item.id for n in needs}
    for old in list(order.packaging):
        if old.packaging_item_id not in wanted:
            order.packaging.remove(old)
    for need in needs:
        row = existing.get(need.item.id)
        if row is None:
            order.packaging.append(
                OrderPackaging(packaging_item_id=need.item.id, planned_qty=need.quantity)
            )
        else:
            row.planned_qty = need.quantity


def _audit_snapshot(order: WorkOrder) -> dict[str, Any]:
    return {
        "operation_number": order.operation_number,
        "order_type": order.order_type,
        "rework_kind": order.rework_kind,
        "related_order_id": order.related_order_id,
        "client_id": order.client_id,
        "razon_social_id": order.razon_social_id,
        "site_id": order.site_id,
        "order_date": order.order_date.isoformat(),
        "status": order.status,
        "base_products": [
            {"product_id": r.product_id, "code": r.code, "liters": str(r.liters)}
            for r in sorted(order.base_products, key=lambda r: r.position)
        ],
        "finished_product_id": order.finished_product_id,
        "finished_code": order.finished_code,
        "finished_liters": str(order.finished_liters),
        "packaging": [
            {"packaging_item_id": r.packaging_item_id, "planned_qty": r.planned_qty}
            for r in order.packaging
        ],
        "labels_planned": order.labels_planned,
        "barcode_mode": order.barcode_mode,
        "previous_lot": order.previous_lot,
        "expiry_date": order.expiry_date.isoformat() if order.expiry_date else None,
        "warnings": order.warnings,
    }


def _audit(
    db: Session, order: WorkOrder, action: str, actor: User,
    before: dict[str, Any] | None, after: dict[str, Any] | None,
) -> None:
    audit_service.record(
        db, user=actor, entity=AUDIT_ENTITY, entity_id=order.id, action=action,
        before=before, after=after,
    )


def _add_comment(db: Session, order: WorkOrder, text: str, actor: User) -> OrderComment:
    comment = OrderComment(order_id=order.id, user_id=actor.id, text=text)
    db.add(comment)
    db.flush()
    _audit(db, order, "comment", actor, None, {"comment_id": comment.id, "text": text})
    return comment


# Numbering ----------------------------------------------------------------------


def _assign_number(db: Session, order: WorkOrder, razon_social: RazonSocial) -> None:
    """BR-19: lock the sequence row, take next_number, increment it."""
    seq = sequence_service.get_sequence(db, order.order_type, lock=True)
    number = seq.next_number
    operation_number = f"{seq.prefix}-{number} {razon_social.code}"
    taken = db.query(
        exists().where(
            or_(
                (WorkOrder.order_type == order.order_type) & (WorkOrder.sequence == number),
                WorkOrder.operation_number == operation_number,
            )
        )
    ).scalar()
    if taken:
        # Only possible after the master admin lowered the next number.
        raise AppError(
            "SEQUENCE_NUMBER_TAKEN",
            f"El número {seq.prefix}-{number} ya fue usado. El administrador maestro debe "
            "ajustar el siguiente número en Configuración → Numeración de órdenes.",
            409,
            {"order_type": order.order_type, "number": number},
        )
    seq.next_number = number + 1
    order.sequence = number
    order.operation_number = operation_number


# Create -------------------------------------------------------------------------


def create_order(db: Session, data: OrderCreate, *, actor: User) -> WorkOrder:
    products = _load_base_products(db, data.base_products, keep_ids=set())
    razon_social = _resolve_razon_social(products, data.razon_social_id)
    rework = _resolve_rework(
        db, order_type=data.order_type, rework_kind=data.rework_kind,
        related_id=data.related_order_id, client_id=data.client_id, self_id=None,
        client_changed=True,
    )
    site = _load_site(db, data.site_id, check_active=True)
    finished = catalog_service.get(db, Product, data.finished_product_id)
    catalog_service.require_active(finished, f"El producto {finished.code}")
    packaging = _load_packaging(db, data.packaging, keep_ids=set())

    order = WorkOrder(
        order_type=data.order_type,
        rework_kind=rework.rework_kind,
        related_order_id=rework.related.id if rework.related else None,
        client_id=rework.client.id if rework.client else None,
        razon_social_id=razon_social.id,
        site_id=site.id,
        order_date=data.order_date or local_today(),
        finished_liters=data.finished_liters or sum((p.liters for p in products), Decimal(0)),
        barcode_mode=data.barcode_mode,
        labels_planned=data.labels_planned,
        previous_lot=data.previous_lot,
        status="created",
        warnings=[],
        created_by=actor.id,
    )
    _set_finished(order, finished)
    if rework.related is not None:
        _copy_expiry(order, rework.related, actor)
    _assign_number(db, order, razon_social)
    for position, need in enumerate(products, start=1):
        order.base_products.append(_new_base_row(need, position))
    for pneed in packaging:
        order.packaging.append(
            OrderPackaging(packaging_item_id=pneed.item.id, planned_qty=pneed.quantity)
        )
    for item in CHECKLIST_ITEMS:
        order.checklist.append(OrderChecklistItem(item=item, checked=False))
    db.add(order)
    db.flush()

    order.warnings = reservation_service.reserve_for_order(db, order, products, packaging) or []
    db.flush()
    _audit(db, order, "create", actor, None, _audit_snapshot(order))
    if data.comment:
        _add_comment(db, order, data.comment, actor)
    db.commit()
    db.refresh(order)
    return order


# Edit ---------------------------------------------------------------------------


def _require_status(order: WorkOrder, allowed: frozenset[str], code: str, message: str) -> None:
    if order.status not in allowed:
        raise AppError(code, message, 409, {"status": order.status})


def update_order(db: Session, order_id: int, data: OrderUpdate, *, actor: User) -> WorkOrder:
    """BR-16: edit while nothing has started; type and razón social are fixed."""
    order = get_order(db, order_id, lock=True)  # serializes concurrent edits
    _require_status(
        order, EDITABLE_STATUSES, "ORDER_NOT_EDITABLE",
        "La orden ya no se puede editar: la producción ya inició o la orden está "
        "cerrada o cancelada. Solo se pueden agregar comentarios.",
    )
    sent = data.model_fields_set
    if "order_type" in sent and data.order_type != order.order_type:
        raise _invalid(
            "IMMUTABLE_FIELD", "El tipo de orden (Trabajo / Retrabajo) no se puede cambiar.",
            {"field": "order_type"},
        )
    if "razon_social_id" in sent and data.razon_social_id != order.razon_social_id:
        raise _invalid(
            "IMMUTABLE_FIELD",
            "La razón social no se puede cambiar: forma parte del número de operación.",
            {"field": "razon_social_id"},
        )
    before = _audit_snapshot(order)
    current_base = {r.product_id: Decimal(r.liters) for r in order.base_products}
    current_pkg = {r.packaging_item_id: r.planned_qty for r in order.packaging}

    # Base products: the order's razón social must stay among theirs (BR-22).
    products: list[ProductNeed] | None = None
    if data.base_products is not None:
        products = _load_base_products(db, data.base_products, keep_ids=set(current_base))
        options = _razon_social_options(products)
        if order.razon_social_id not in options:
            raise _invalid(
                "RAZON_SOCIAL_MISMATCH",
                "Al menos un producto base debe pertenecer a la razón social de la orden "
                "(no se puede cambiar porque forma parte del número de operación).",
                {"razon_social_id": order.razon_social_id},
            )

    # Rework kind / related order / client (BR-20, BR-21).
    old_kind, old_related = order.rework_kind, order.related_order_id
    rework = _resolve_rework(
        db,
        order_type=order.order_type,
        rework_kind=data.rework_kind if "rework_kind" in sent else order.rework_kind,
        related_id=(
            data.related_order_id if "related_order_id" in sent else order.related_order_id
        ),
        client_id=data.client_id if "client_id" in sent else order.client_id,
        self_id=order.id,
        client_changed="client_id" in sent and data.client_id != order.client_id,
    )
    order.rework_kind = rework.rework_kind
    order.related_order_id = rework.related.id if rework.related else None
    order.client_id = rework.client.id if rework.client else None
    if rework.related is not None and (
        old_kind != "previous_order" or old_related != rework.related.id
    ):
        _copy_expiry(order, rework.related, actor)
    elif old_kind == "previous_order" and rework.rework_kind != "previous_order":
        order.expiry_date = None  # the copied expiry no longer applies
        order.expiry_set_by = None
        order.expiry_set_at = None

    site_changed = "site_id" in sent and data.site_id is not None and data.site_id != order.site_id
    if site_changed:
        order.site_id = _load_site(db, data.site_id, check_active=True).id
    if "order_date" in sent and data.order_date is not None:
        order.order_date = data.order_date
    new_finished = data.finished_product_id
    finished_changed = new_finished is not None and new_finished != order.finished_product_id
    liters_changed = (
        data.finished_liters is not None
        and Decimal(data.finished_liters) != Decimal(order.finished_liters)
    )
    if finished_changed and new_finished is not None:
        finished = catalog_service.get(db, Product, new_finished)
        catalog_service.require_active(finished, f"El producto {finished.code}")
        _set_finished(order, finished)
    if data.finished_liters is not None:
        order.finished_liters = data.finished_liters
    if data.barcode_mode is not None:
        order.barcode_mode = data.barcode_mode
    if "labels_planned" in sent:
        order.labels_planned = data.labels_planned
    if "previous_lot" in sent:
        order.previous_lot = data.previous_lot

    packaging: list[PackagingNeed] | None = None
    if data.packaging is not None:
        packaging = _load_packaging(db, data.packaging, keep_ids=set(current_pkg))

    # Reservations: re-check and replace only what changed (FR-INV "on edit").
    products_changed = site_changed or (
        products is not None
        and {n.product.id: n.liters for n in products} != current_base
    )
    packaging_changed = site_changed or (
        packaging is not None and {n.item.id: n.quantity for n in packaging} != current_pkg
    )
    if products is not None:
        _sync_base_rows(order, products)
    if packaging is not None:
        _sync_packaging_rows(order, packaging)
    db.flush()

    if products_changed and products is None:
        products = [
            ProductNeed(product=catalog_service.get(db, Product, r.product_id), liters=r.liters)
            for r in order.base_products
        ]
    if packaging_changed and packaging is None:
        packaging = [
            PackagingNeed(
                item=catalog_service.get(db, PackagingItem, r.packaging_item_id),
                quantity=r.planned_qty,
            )
            for r in order.packaging
        ]
    warnings = reservation_service.reserve_for_order(
        db, order,
        products if products_changed else None,
        packaging if packaging_changed else None,
    )
    if warnings is not None:
        order.warnings = warnings
    db.flush()

    # BR-16: the split no longer matches -> delete it; the Production manager
    # assigns again. Then created <-> assigned is recomputed (the expiry may
    # also have been cleared by a rework kind change).
    removed: list[dict[str, Any]] = []
    if products_changed or finished_changed or liters_changed:
        removed = assignment_service.delete_for_edit(db, order)
    assignment_service.refresh_pre_production_status(db, order)

    after = _audit_snapshot(order)
    if removed:
        after["removed_assignments"] = removed
    if after != before:
        _audit(db, order, "update", actor, before, after)
    if data.comment:
        _add_comment(db, order, data.comment, actor)
    db.commit()
    db.refresh(order)
    return order


# Delete / cancel ----------------------------------------------------------------


def delete_order(db: Session, order_id: int, *, actor: User) -> None:
    """BR-17: only in Creada. The number is not reused (BR-19 leaves a gap)."""
    order = get_order(db, order_id, lock=True)
    _require_status(
        order, DELETABLE_STATUSES, "INVALID_TRANSITION",
        "Solo se pueden eliminar órdenes en estado Creada.",
    )
    before = _audit_snapshot(order)
    released = reservation_service.release_for_order(db, order)  # BR-10
    assignment_service.delete_for_edit(db, order)
    _audit(db, order, "delete", actor, before, {"released_reservations": released})
    db.delete(order)
    db.commit()


def cancel_order(db: Session, order_id: int, reason: str, *, actor: User) -> WorkOrder:
    """BR-17: Creada or Asignada, mandatory reason; releases reservations (BR-10)."""
    order = get_order(db, order_id, lock=True)
    _require_status(
        order, CANCELLABLE_STATUSES, "INVALID_TRANSITION",
        "Solo se pueden cancelar órdenes antes de que inicie la producción.",
    )
    before_status = order.status
    cancelled_assignments = assignment_service.cancel_for_order(db, order, actor)
    released = reservation_service.release_for_order(db, order)
    order.status = "cancelled"
    order.cancelled_by = actor.id
    order.cancelled_at = utc_now()
    order.cancel_reason = reason
    db.flush()
    _audit(
        db, order, "cancel", actor, {"status": before_status},
        {
            "status": "cancelled", "cancel_reason": reason, "released_reservations": released,
            "cancelled_assignments": cancelled_assignments,
        },
    )
    db.commit()
    db.refresh(order)
    return order


# Expiry (BR-20) -----------------------------------------------------------------


def _first_of_month(value: date) -> date:
    """TODO(OPEN-4): stored as the 1st of the month, shown MM/AAAA."""
    return value.replace(day=1)


def set_expiry(db: Session, order_id: int, value: date | None, *, actor: User) -> WorkOrder:
    """Trabajo: editable (or cleared) until production starts. Retrabajo de
    orden anterior: copied and locked. Retrabajo de inventario propio: entered
    once, then locked. Setting it may complete Asignada (BR-20)."""
    order = get_order(db, order_id, lock=True)
    _require_status(
        order, EXPIRY_STATUSES, "EXPIRY_LOCKED",
        "La fecha de caducidad ya no se puede cambiar: la producción ya inició o la orden "
        "está cerrada o cancelada.",
    )
    if expiry_locked(order):
        raise AppError(
            "EXPIRY_LOCKED", "La fecha de caducidad de este retrabajo no se puede cambiar.", 409,
            {"rework_kind": order.rework_kind},
        )
    if value is None and order.order_type == "retrabajo":
        raise _invalid("EXPIRY_REQUIRED", "Ingrese la fecha de caducidad.")
    new_value = _first_of_month(value) if value is not None else None
    before = {
        "expiry_date": order.expiry_date.isoformat() if order.expiry_date else None,
        "status": order.status,
    }
    order.expiry_date = new_value
    order.expiry_set_by = actor.id
    order.expiry_set_at = utc_now()
    db.flush()
    assignment_service.refresh_pre_production_status(db, order)
    after = {
        "expiry_date": new_value.isoformat() if new_value else None,
        "status": order.status,
    }
    if after != before:
        _audit(db, order, "expiry", actor, before, after)
    db.commit()
    db.refresh(order)
    return order


# Traceability (BR-24) and materials ------------------------------------------------


def _require_traceability(order: WorkOrder) -> None:
    _require_status(
        order, TRACEABILITY_STATUSES, "ORDER_READ_ONLY",
        "La orden está cerrada o cancelada: solo se pueden agregar comentarios.",
    )


def update_checklist(db: Session, order_id: int, data: ChecklistIn, *, actor: User) -> WorkOrder:
    """Each change records who and when (also when an item is unchecked)."""
    order = get_order(db, order_id, lock=True)
    _require_traceability(order)
    rows = {c.item: c for c in order.checklist}
    now = utc_now()
    changes: dict[str, list[bool]] = {}
    for entry in data.items:
        row = rows.get(entry.item)
        if row is None:  # orders always have the 4 rows; be lenient with old data
            row = OrderChecklistItem(item=entry.item, checked=False)
            order.checklist.append(row)
        if bool(row.checked) != entry.checked:
            changes[entry.item] = [bool(row.checked), entry.checked]
            row.checked = entry.checked
            row.checked_by = actor.id
            row.checked_at = now
    db.flush()
    if changes:
        _audit(
            db, order, "checklist", actor,
            {k: v[0] for k, v in changes.items()}, {k: v[1] for k, v in changes.items()},
        )
    db.commit()
    db.refresh(order)
    return order


def update_traceability(
    db: Session, order_id: int, data: TraceabilityIn, *, actor: User
) -> WorkOrder:
    """Lote posterior (who/when recorded) and lote anterior. TODO(OPEN-4)."""
    order = get_order(db, order_id, lock=True)
    _require_traceability(order)
    sent = data.model_fields_set
    before: dict[str, Any] = {}
    after: dict[str, Any] = {}
    if "new_lot" in sent and data.new_lot != order.new_lot:
        before["new_lot"], after["new_lot"] = order.new_lot, data.new_lot
        order.new_lot = data.new_lot
        order.new_lot_by = actor.id
        order.new_lot_at = utc_now()
    if "previous_lot" in sent and data.previous_lot != order.previous_lot:
        before["previous_lot"], after["previous_lot"] = order.previous_lot, data.previous_lot
        order.previous_lot = data.previous_lot
    db.flush()
    if after:
        _audit(db, order, "traceability", actor, before, after)
    db.commit()
    db.refresh(order)
    return order


def update_materials(db: Session, order_id: int, data: MaterialsIn, *, actor: User) -> WorkOrder:
    """Actual packaging and labels used (who/when recorded). Packaging is
    consumed when the order completes; changes after that (before closing)
    write only the difference (BR-8)."""
    order = get_order(db, order_id, lock=True)
    _require_traceability(order)
    rows = {p.packaging_item_id: p for p in order.packaging}
    now = utc_now()
    before: dict[str, Any] = {}
    after: dict[str, Any] = {}
    for entry in data.packaging:
        row = rows.get(entry.packaging_item_id)
        if row is None:
            raise _invalid(
                "PACKAGING_NOT_IN_ORDER", "El material no forma parte de la orden.",
                {"packaging_item_id": entry.packaging_item_id},
            )
        if row.actual_qty != entry.actual_qty:
            key = f"packaging_{row.packaging_item_id}"
            before[key], after[key] = row.actual_qty, entry.actual_qty
            row.actual_qty = entry.actual_qty
            row.actual_by = actor.id
            row.actual_at = now
    if "labels_actual" in data.model_fields_set and data.labels_actual != order.labels_actual:
        before["labels_actual"], after["labels_actual"] = order.labels_actual, data.labels_actual
        order.labels_actual = data.labels_actual
        order.labels_actual_by = actor.id
        order.labels_actual_at = now
    db.flush()
    if after and order.status == "completed":
        corrections = assignment_service.correct_packaging(db, order, actor)
        if corrections:
            after["stock_corrections"] = corrections
    if after:
        _audit(db, order, "materials", actor, before, after)
    db.commit()
    db.refresh(order)
    return order


# Closing (BR-11) -----------------------------------------------------------------------


def close_order(db: Session, order_id: int, note: str | None, *, actor: User) -> WorkOrder:
    """Completada -> Cerrada. Allowed with any difference and with incomplete
    checklist/lot/materials (the dialog lists them); optional note."""
    order = get_order(db, order_id, lock=True)
    _require_status(
        order, frozenset({"completed"}), "INVALID_TRANSITION",
        "Solo se pueden cerrar órdenes completadas.",
    )
    live = assignment_service.order_assignments(db, order.id, include_cancelled=False)
    diff = production_service.difference(db, order, live)
    order.status = "closed"
    order.closed_by = actor.id
    order.closed_at = utc_now()
    order.close_note = note
    db.flush()
    _audit(
        db, order, "close", actor, {"status": "completed"},
        {
            "status": "closed", "close_note": note, "difference": str(diff.difference),
            "within_range": diff.within_range, "missing": close_missing(order),
        },
    )
    db.commit()
    db.refresh(order)
    return order


# Comments / history -------------------------------------------------------------


def add_comment(db: Session, order_id: int, text: str, *, actor: User) -> OrderComment:
    """Append-only, allowed in any status (including closed and cancelled)."""
    order = get_order(db, order_id)
    comment = _add_comment(db, order, text, actor)
    db.commit()
    db.refresh(comment)
    return comment


def _user_names(db: Session, ids: set[int | None]) -> dict[int, str]:
    clean = {i for i in ids if i is not None}
    if not clean:
        return {}
    rows = db.query(User.id, User.full_name).filter(User.id.in_(clean)).all()
    return {user_id: name for user_id, name in rows}


def list_comments(db: Session, order_id: int, *, newest_first: bool = True) -> list[CommentOut]:
    order = get_order(db, order_id)
    rows = sorted(order.comments, key=lambda c: c.id, reverse=newest_first)
    names = _user_names(db, {c.user_id for c in rows})
    return [
        CommentOut(
            id=c.id, user_id=c.user_id, user_name=names.get(c.user_id, ""), text=c.text,
            created_at=c.created_at,
        )
        for c in rows
    ]


def history(db: Session, order_id: int) -> list[HistoryEntry]:
    order = get_order(db, order_id)
    rows = (
        db.query(AuditLog)
        .filter(AuditLog.entity == AUDIT_ENTITY, AuditLog.entity_id == order.id)
        .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        .all()
    )
    names = _user_names(db, {r.user_id for r in rows})
    return [
        HistoryEntry(
            id=r.id, created_at=r.created_at, user_id=r.user_id,
            user_name=names.get(r.user_id) if r.user_id else None,
            action=r.action, before=r.before, after=r.after,
        )
        for r in rows
    ]


# Read models --------------------------------------------------------------------


def close_missing(order: WorkOrder) -> list[MissingForClose]:
    """What the close dialog lists as incomplete (never blocks closing, BR-11)."""
    missing: list[MissingForClose] = []
    if not all(c.checked for c in order.checklist):
        missing.append("checklist")
    if not order.new_lot:
        missing.append("new_lot")
    if any(p.actual_qty is None for p in order.packaging):
        missing.append("materials")
    if order.labels_actual is None:
        missing.append("labels")
    return missing


def order_out(db: Session, order: WorkOrder) -> OrderOut:
    names = _user_names(
        db,
        {
            order.created_by, order.cancelled_by, order.closed_by, order.labels_actual_by,
            order.new_lot_by, order.expiry_set_by,
        }
        | {p.actual_by for p in order.packaging}
        | {c.checked_by for c in order.checklist},
    )
    assignments = assignment_service.order_assignments(db, order.id)
    live = [a for a in assignments if a.status != "cancelled"]
    ended = order.status in production_service.ENDED_STATUSES
    client = db.get(Client, order.client_id) if order.client_id else None
    rs = db.get(RazonSocial, order.razon_social_id)
    site = db.get(Site, order.site_id)
    related = db.get(WorkOrder, order.related_order_id) if order.related_order_id else None
    pkg_items = {
        p.id: p
        for p in db.query(PackagingItem).filter(
            PackagingItem.id.in_([r.packaging_item_id for r in order.packaging])
        )
    }
    base = sorted(order.base_products, key=lambda r: r.position)
    checklist_order = {item: i for i, item in enumerate(CHECKLIST_ITEMS)}
    assert rs is not None and site is not None
    return OrderOut(
        id=order.id,
        order_type=order.order_type,  # type: ignore[arg-type]
        sequence=order.sequence,
        operation_number=order.operation_number,
        rework_kind=order.rework_kind,  # type: ignore[arg-type]
        related_order_id=order.related_order_id,
        related_operation_number=related.operation_number if related else None,
        client_id=order.client_id,
        client_name=client.name if client else None,
        razon_social_id=rs.id,
        razon_social_code=rs.code,
        razon_social_name=rs.name,
        site_id=site.id,
        site_name=site.name,
        order_date=order.order_date,
        base_products=[
            BaseProductOut(
                position=r.position, product_id=r.product_id, code=r.code, name=r.name,
                provider=r.provider, presentation=r.presentation,
                razon_social_code=r.razon_social_code, liters=r.liters,
            )
            for r in base
        ],
        base_liters_total=sum((Decimal(r.liters) for r in base), Decimal(0)),
        finished_product_id=order.finished_product_id,
        finished_code=order.finished_code,
        finished_name=order.finished_name,
        finished_provider=order.finished_provider,
        finished_presentation=order.finished_presentation,
        finished_liters=order.finished_liters,
        packaging=[
            PackagingOut(
                packaging_item_id=r.packaging_item_id,
                code=pkg_items[r.packaging_item_id].code,
                description=pkg_items[r.packaging_item_id].description,
                planned_qty=r.planned_qty, actual_qty=r.actual_qty,
                actual_by_name=names.get(r.actual_by) if r.actual_by else None,
                actual_at=r.actual_at,
            )
            for r in order.packaging
        ],
        checklist=[
            ChecklistOut(
                item=c.item, checked=c.checked,
                checked_by_name=names.get(c.checked_by) if c.checked_by else None,
                checked_at=c.checked_at,
            )
            for c in sorted(order.checklist, key=lambda c: checklist_order.get(c.item, 99))
        ],
        labels_planned=order.labels_planned,
        labels_actual=order.labels_actual,
        barcode_mode=order.barcode_mode,  # type: ignore[arg-type]
        previous_lot=order.previous_lot,
        new_lot=order.new_lot,
        expiry_date=order.expiry_date,
        expiry_locked=expiry_locked(order),
        status=order.status,  # type: ignore[arg-type]
        warnings=order.warnings or [],
        created_by=order.created_by,
        created_by_name=names.get(order.created_by, ""),
        created_at=order.created_at,
        updated_at=order.updated_at,
        cancelled_by_name=names.get(order.cancelled_by) if order.cancelled_by else None,
        cancelled_at=order.cancelled_at,
        cancel_reason=order.cancel_reason,
        closed_by_name=names.get(order.closed_by) if order.closed_by else None,
        closed_at=order.closed_at,
        close_note=order.close_note,
        can_edit=order.status in EDITABLE_STATUSES,
        can_cancel=order.status in CANCELLABLE_STATUSES,
        can_delete=order.status in DELETABLE_STATUSES,
        can_set_expiry=order.status in EXPIRY_STATUSES and not expiry_locked(order),
        can_assign=order.status in assignment_service.PRE_PRODUCTION_STATUSES,
        can_edit_traceability=order.status in TRACEABILITY_STATUSES,
        can_close=order.status == "completed",
        assignments=production_service.assignment_rows(db, assignments),
        assigned_liters=assignment_service.planned_total(live),
        missing_for_assign=(
            production_service.missing_for_assign(order, live)
            if order.status == "created" else []
        ),
        difference=production_service.difference(db, order, live) if ended else None,
        close_missing=close_missing(order) if order.status in ("completed", "closed") else [],
        labels_actual_by_name=names.get(order.labels_actual_by) if order.labels_actual_by else None,
        labels_actual_at=order.labels_actual_at,
        new_lot_by_name=names.get(order.new_lot_by) if order.new_lot_by else None,
        new_lot_at=order.new_lot_at,
        expiry_set_by_name=names.get(order.expiry_set_by) if order.expiry_set_by else None,
        expiry_set_at=order.expiry_set_at,
    )


def list_orders(
    db: Session,
    *,
    statuses: list[str] | None = None,
    order_type: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    client_id: int | None = None,
    razon_social_id: int | None = None,
    product_id: int | None = None,
    site_id: int | None = None,
    search: str | None = None,
    page: int = 1,
    page_size: int = 50,
) -> tuple[list[OrderListItem], int]:
    """FR-ORD-2. `product_id` matches any base product or the finished product."""
    query = (
        db.query(WorkOrder, Client.name, RazonSocial.code, Site.name)
        .outerjoin(Client, Client.id == WorkOrder.client_id)
        .join(RazonSocial, RazonSocial.id == WorkOrder.razon_social_id)
        .join(Site, Site.id == WorkOrder.site_id)
    )
    if statuses:
        query = query.filter(WorkOrder.status.in_(statuses))
    if order_type:
        query = query.filter(WorkOrder.order_type == order_type)
    if date_from:
        query = query.filter(WorkOrder.order_date >= date_from)
    if date_to:
        query = query.filter(WorkOrder.order_date <= date_to)
    if client_id is not None:
        query = query.filter(WorkOrder.client_id == client_id)
    if razon_social_id is not None:
        query = query.filter(WorkOrder.razon_social_id == razon_social_id)
    if site_id is not None:
        query = query.filter(WorkOrder.site_id == site_id)
    if product_id is not None:
        in_base = select(OrderBaseProduct.order_id).where(
            OrderBaseProduct.product_id == product_id
        )
        query = query.filter(
            or_(WorkOrder.finished_product_id == product_id, WorkOrder.id.in_(in_base))
        )
    if search:
        query = query.filter(WorkOrder.operation_number.ilike(f"%{search.strip()}%"))

    total = query.count()
    rows = (
        query.order_by(WorkOrder.created_at.desc(), WorkOrder.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    items = [
        OrderListItem(
            id=o.id,
            order_type=o.order_type,  # type: ignore[arg-type]
            operation_number=o.operation_number,
            rework_kind=o.rework_kind,  # type: ignore[arg-type]
            status=o.status,  # type: ignore[arg-type]
            order_date=o.order_date,
            client_name=client_name,
            razon_social_code=rs_code,
            site_name=site_name,
            base_products=[f"{r.code} — {r.name}" for r in o.base_products],
            finished_code=o.finished_code,
            finished_name=o.finished_name,
            finished_liters=o.finished_liters,
            has_warnings=bool(o.warnings),
            created_at=o.created_at,
        )
        for o, client_name, rs_code, site_name in rows
    ]
    return items, total


def print_data(db: Session, order_id: int) -> PrintData:
    """FR-ORD-6: everything the printable form needs."""
    order = get_order(db, order_id)
    out = order_out(db, order)
    latest = max(
        (a for a in out.assignments if a.status != "cancelled"),
        key=lambda a: a.assigned_at, default=None,
    )
    return PrintData(
        order=out,
        comments=list_comments(db, order_id, newest_first=False),
        created=Signature(name=out.created_by_name, at=order.created_at),
        assigned=Signature(name=latest.assigned_by_name, at=latest.assigned_at) if latest else None,
        closed=(
            Signature(name=out.closed_by_name, at=order.closed_at)
            if out.closed_by_name and order.closed_at else None
        ),
        barcodes={
            "operation_number": order.operation_number,
            "finished_code": order.finished_code,
        },
    )
