"""Catalog CRUD: sites, clients, products, packaging items (FR-CAT-1..4, FR-CAT-6).

Machines live in machine_service (API key handling). Rules enforced here:
- unique codes (and unique site names) -> 409 `DUPLICATE_CODE` / `DUPLICATE_NAME`;
- no hard deletes; deactivation through `is_active` (FR-CAT-6);
- exactly one active default site (FR-CAT-4);
- every write is audited (BR-18).
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, TypeVar

from pydantic import BaseModel
from sqlalchemy import or_
from sqlalchemy.orm import InstrumentedAttribute, Session

from app.core.errors import AppError, not_found
from app.db.base import Base
from app.models.catalogs import Client, PackagingItem, Product, Site
from app.models.user import User
from app.schemas.catalogs import (
    ClientCreate,
    ClientUpdate,
    PackagingItemCreate,
    PackagingItemUpdate,
    ProductCreate,
    ProductUpdate,
    SiteCreate,
    SiteUpdate,
)
from app.services import audit_service, settings_service

M = TypeVar("M", bound=Base)

# entity -> (Spanish label for messages, audit entity name, snapshot fields)
_META: dict[type[Base], tuple[str, str, tuple[str, ...]]] = {
    Site: ("Sitio", "site", ("name", "is_default", "is_active")),
    Client: ("Cliente", "client", ("name", "code", "is_active")),
    Product: (
        "Producto",
        "product",
        ("code", "name", "provider", "presentation", "container_liters", "is_active"),
    ),
    PackagingItem: (
        "Material de empaque",
        "packaging_item",
        ("code", "description", "category", "low_stock_threshold", "is_active"),
    ),
}


def _json_value(v: Any) -> Any:
    return str(v) if isinstance(v, Decimal) else v


def snapshot(obj: Base, fields: tuple[str, ...]) -> dict[str, Any]:
    return {f: _json_value(getattr(obj, f)) for f in fields}


def _meta(model: type[Base]) -> tuple[str, str, tuple[str, ...]]:
    return _META[model]


# Generic helpers -------------------------------------------------------------


def get(db: Session, model: type[M], item_id: int) -> M:
    obj = db.get(model, item_id)
    if obj is None:
        label = _META[model][0] if model in _META else "Registro"
        raise not_found(label)
    return obj



def list_items(
    db: Session,
    model: type[M],
    *,
    search_fields: list[InstrumentedAttribute],
    order_by: InstrumentedAttribute,
    search: str | None = None,
    active: bool | None = None,
    page: int = 1,
    page_size: int = 50,
    extra_filters: list[Any] | None = None,
) -> tuple[list[M], int]:
    query = db.query(model)
    if search:
        like = f"%{search.strip()}%"
        query = query.filter(or_(*[f.ilike(like) for f in search_fields]))
    if active is not None:
        query = query.filter(model.is_active.is_(active))  # type: ignore[attr-defined]
    for f in extra_filters or []:
        query = query.filter(f)
    total = query.count()
    items = query.order_by(order_by).offset((page - 1) * page_size).limit(page_size).all()
    return items, total


def ensure_unique(
    db: Session,
    model: type[Base],
    column: InstrumentedAttribute,
    value: str,
    *,
    exclude_id: int | None = None,
    code: str = "DUPLICATE_CODE",
    message: str = "Ya existe un registro con ese código.",
) -> None:
    query = db.query(model).filter(column == value)
    if exclude_id is not None:
        query = query.filter(model.id != exclude_id)  # type: ignore[attr-defined]
    if query.first() is not None:
        raise AppError(code, message, 409, {"value": value})


def apply_changes(obj: Base, data: BaseModel, nullable: set[str] | None = None) -> None:
    """PATCH semantics: only fields the client sent; `None` clears only nullable fields."""
    nullable = nullable or set()
    for field, value in data.model_dump(exclude_unset=True).items():
        if value is None and field not in nullable:
            continue
        setattr(obj, field, value)


def _create(db: Session, obj: M, *, actor: User) -> M:
    _, entity, fields = _meta(type(obj))
    db.add(obj)
    db.flush()
    audit_service.record(
        db, user=actor, entity=entity, entity_id=obj.id,  # type: ignore[attr-defined]
        action="create", before=None, after=snapshot(obj, fields),
    )
    db.commit()
    db.refresh(obj)
    return obj


def _audit_update(db: Session, obj: Base, before: dict[str, Any], *, actor: User) -> None:
    _, entity, fields = _meta(type(obj))
    after = snapshot(obj, fields)
    if after == before:
        return
    action = "update"
    if before.get("is_active") is True and after.get("is_active") is False:
        action = "deactivate"
    elif before.get("is_active") is False and after.get("is_active") is True:
        action = "activate"
    audit_service.record(
        db, user=actor, entity=entity, entity_id=obj.id,  # type: ignore[attr-defined]
        action=action, before=before, after=after,
    )


def require_active(obj: Base, label: str) -> None:
    """FR-CAT-6: inactive items cannot be selected in new records."""
    if not getattr(obj, "is_active", True):
        raise AppError(
            "INACTIVE_ITEM",
            f"{label} está inactivo y no puede seleccionarse.",
            422,
            {"id": getattr(obj, "id", None)},
        )


# Sites -----------------------------------------------------------------------


def get_default_site(db: Session) -> Site | None:
    return db.query(Site).filter(Site.is_default.is_(True)).first()


def _make_default(db: Session, site: Site) -> None:
    for other in db.query(Site).filter(Site.is_default.is_(True), Site.id != site.id).all():
        other.is_default = False
    site.is_default = True


def _sync_default_setting(db: Session) -> None:
    default = get_default_site(db)
    settings_service.set_value_no_commit(db, "default_site_id", default.id if default else None)


def create_site(db: Session, data: SiteCreate, *, actor: User) -> Site:
    ensure_unique(
        db, Site, Site.name, data.name,
        code="DUPLICATE_NAME", message="Ya existe un sitio con ese nombre.",
    )
    site = Site(name=data.name, is_default=False, is_active=True)
    db.add(site)
    db.flush()
    # The first site always becomes the default (exactly one default, FR-CAT-4).
    if data.is_default or get_default_site(db) is None:
        _make_default(db, site)
    db.flush()
    _sync_default_setting(db)
    return _create(db, site, actor=actor)


def update_site(db: Session, site_id: int, data: SiteUpdate, *, actor: User) -> Site:
    site = get(db, Site, site_id)
    before = snapshot(site, _META[Site][2])

    if data.name is not None and data.name != site.name:
        ensure_unique(
            db, Site, Site.name, data.name, exclude_id=site.id,
            code="DUPLICATE_NAME", message="Ya existe un sitio con ese nombre.",
        )
        site.name = data.name

    if data.is_default is False and site.is_default:
        raise AppError(
            "DEFAULT_SITE_REQUIRED",
            "Debe existir un sitio por defecto. Marque otro sitio como predeterminado.",
            409,
        )
    if data.is_active is False and (site.is_default or data.is_default):
        raise AppError(
            "DEFAULT_SITE_INACTIVE",
            "No se puede desactivar el sitio por defecto.",
            409,
        )
    if data.is_active is not None:
        site.is_active = data.is_active
    if data.is_default:
        if not site.is_active:
            raise AppError(
                "DEFAULT_SITE_INACTIVE", "El sitio por defecto debe estar activo.", 409
            )
        _make_default(db, site)

    db.flush()
    _sync_default_setting(db)
    _audit_update(db, site, before, actor=actor)
    db.commit()
    db.refresh(site)
    return site


# Clients ---------------------------------------------------------------------


def create_client(db: Session, data: ClientCreate, *, actor: User) -> Client:
    ensure_unique(
        db, Client, Client.code, data.code, message="Ya existe un cliente con ese código."
    )
    return _create(db, Client(name=data.name, code=data.code, is_active=True), actor=actor)


def update_client(db: Session, client_id: int, data: ClientUpdate, *, actor: User) -> Client:
    client = get(db, Client, client_id)
    before = snapshot(client, _META[Client][2])
    if data.code is not None:
        ensure_unique(
            db, Client, Client.code, data.code, exclude_id=client.id,
            message="Ya existe un cliente con ese código.",
        )
    apply_changes(client, data)
    db.flush()
    _audit_update(db, client, before, actor=actor)
    db.commit()
    db.refresh(client)
    return client


# Products --------------------------------------------------------------------


def create_product(db: Session, data: ProductCreate, *, actor: User) -> Product:
    ensure_unique(
        db, Product, Product.code, data.code, message="Ya existe un producto con ese código."
    )
    product = Product(**data.model_dump(), is_active=True)
    return _create(db, product, actor=actor)


def update_product(
    db: Session, product_id: int, data: ProductUpdate, *, actor: User
) -> Product:
    product = get(db, Product, product_id)
    before = snapshot(product, _META[Product][2])
    if data.code is not None:
        ensure_unique(
            db, Product, Product.code, data.code, exclude_id=product.id,
            message="Ya existe un producto con ese código.",
        )
    apply_changes(product, data, nullable={"container_liters"})
    db.flush()
    _audit_update(db, product, before, actor=actor)
    db.commit()
    db.refresh(product)
    return product


# Packaging items -------------------------------------------------------------


def create_packaging_item(
    db: Session, data: PackagingItemCreate, *, actor: User
) -> PackagingItem:
    ensure_unique(
        db, PackagingItem, PackagingItem.code, data.code,
        message="Ya existe un material de empaque con ese código.",
    )
    item = PackagingItem(**data.model_dump(), is_active=True)
    return _create(db, item, actor=actor)


def update_packaging_item(
    db: Session, item_id: int, data: PackagingItemUpdate, *, actor: User
) -> PackagingItem:
    item = get(db, PackagingItem, item_id)
    before = snapshot(item, _META[PackagingItem][2])
    if data.code is not None:
        ensure_unique(
            db, PackagingItem, PackagingItem.code, data.code, exclude_id=item.id,
            message="Ya existe un material de empaque con ese código.",
        )
    apply_changes(item, data)
    db.flush()
    _audit_update(db, item, before, actor=actor)
    db.commit()
    db.refresh(item)
    return item
