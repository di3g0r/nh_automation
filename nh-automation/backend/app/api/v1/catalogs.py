"""Catalog endpoints (FR-CAT): products, packaging items, clients, sites, machines.

Writes need `catalogs.manage`. Reads are also open to `inventory.view` so the
warehouse supervisor can pick items in receipts/adjustments. No DELETE
endpoints: items are deactivated with PATCH {"is_active": false} (FR-CAT-6).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_any_permission, require_permission
from app.core.permissions import Permission
from app.models.catalogs import Client, Machine, PackagingItem, Product, Site
from app.models.user import User
from app.schemas.catalogs import (
    ClientCreate,
    ClientOut,
    ClientUpdate,
    MachineCreate,
    MachineOut,
    MachineUpdate,
    MachineWithKeyOut,
    PackagingCategory,
    PackagingItemCreate,
    PackagingItemOut,
    PackagingItemUpdate,
    ProductCreate,
    ProductOut,
    ProductUpdate,
    SiteCreate,
    SiteOut,
    SiteUpdate,
)
from app.schemas.common import Page
from app.services import catalog_service, machine_service

router = APIRouter(tags=["catalogs"])

_manage = require_permission(Permission.CATALOGS_MANAGE)
_read = require_any_permission(Permission.CATALOGS_MANAGE, Permission.INVENTORY_VIEW)

_PAGE = Query(1, ge=1)
_PAGE_SIZE = Query(50, ge=1, le=500)


# Products --------------------------------------------------------------------


@router.get("/products", response_model=Page[ProductOut])
def list_products(
    search: str | None = None,
    active: bool | None = None,
    page: int = _PAGE,
    page_size: int = _PAGE_SIZE,
    db: Session = Depends(get_db),
    _actor: User = Depends(_read),
) -> Page[ProductOut]:
    items, total = catalog_service.list_items(
        db, Product,
        search_fields=[Product.code, Product.name, Product.provider],
        order_by=Product.code, search=search, active=active, page=page, page_size=page_size,
    )
    return Page[ProductOut](items=[ProductOut.model_validate(i) for i in items], total=total)


@router.post("/products", response_model=ProductOut, status_code=201)
def create_product(
    payload: ProductCreate, db: Session = Depends(get_db), actor: User = Depends(_manage)
) -> ProductOut:
    return ProductOut.model_validate(catalog_service.create_product(db, payload, actor=actor))


@router.get("/products/{item_id}", response_model=ProductOut)
def get_product(
    item_id: int, db: Session = Depends(get_db), _actor: User = Depends(_read)
) -> ProductOut:
    return ProductOut.model_validate(catalog_service.get(db, Product, item_id))


@router.patch("/products/{item_id}", response_model=ProductOut)
def update_product(
    item_id: int,
    payload: ProductUpdate,
    db: Session = Depends(get_db),
    actor: User = Depends(_manage),
) -> ProductOut:
    return ProductOut.model_validate(
        catalog_service.update_product(db, item_id, payload, actor=actor)
    )


# Packaging items -------------------------------------------------------------


@router.get("/packaging-items", response_model=Page[PackagingItemOut])
def list_packaging_items(
    search: str | None = None,
    active: bool | None = None,
    category: PackagingCategory | None = None,
    page: int = _PAGE,
    page_size: int = _PAGE_SIZE,
    db: Session = Depends(get_db),
    _actor: User = Depends(_read),
) -> Page[PackagingItemOut]:
    items, total = catalog_service.list_items(
        db, PackagingItem,
        search_fields=[PackagingItem.code, PackagingItem.description],
        order_by=PackagingItem.code, search=search, active=active,
        page=page, page_size=page_size,
        extra_filters=[PackagingItem.category == category] if category else None,
    )
    return Page[PackagingItemOut](
        items=[PackagingItemOut.model_validate(i) for i in items], total=total
    )


@router.post("/packaging-items", response_model=PackagingItemOut, status_code=201)
def create_packaging_item(
    payload: PackagingItemCreate, db: Session = Depends(get_db), actor: User = Depends(_manage)
) -> PackagingItemOut:
    return PackagingItemOut.model_validate(
        catalog_service.create_packaging_item(db, payload, actor=actor)
    )


@router.get("/packaging-items/{item_id}", response_model=PackagingItemOut)
def get_packaging_item(
    item_id: int, db: Session = Depends(get_db), _actor: User = Depends(_read)
) -> PackagingItemOut:
    return PackagingItemOut.model_validate(catalog_service.get(db, PackagingItem, item_id))


@router.patch("/packaging-items/{item_id}", response_model=PackagingItemOut)
def update_packaging_item(
    item_id: int,
    payload: PackagingItemUpdate,
    db: Session = Depends(get_db),
    actor: User = Depends(_manage),
) -> PackagingItemOut:
    return PackagingItemOut.model_validate(
        catalog_service.update_packaging_item(db, item_id, payload, actor=actor)
    )


# Clients ---------------------------------------------------------------------


@router.get("/clients", response_model=Page[ClientOut])
def list_clients(
    search: str | None = None,
    active: bool | None = None,
    page: int = _PAGE,
    page_size: int = _PAGE_SIZE,
    db: Session = Depends(get_db),
    _actor: User = Depends(_read),
) -> Page[ClientOut]:
    items, total = catalog_service.list_items(
        db, Client, search_fields=[Client.name, Client.code], order_by=Client.name,
        search=search, active=active, page=page, page_size=page_size,
    )
    return Page[ClientOut](items=[ClientOut.model_validate(i) for i in items], total=total)


@router.post("/clients", response_model=ClientOut, status_code=201)
def create_client(
    payload: ClientCreate, db: Session = Depends(get_db), actor: User = Depends(_manage)
) -> ClientOut:
    return ClientOut.model_validate(catalog_service.create_client(db, payload, actor=actor))


@router.get("/clients/{item_id}", response_model=ClientOut)
def get_client(
    item_id: int, db: Session = Depends(get_db), _actor: User = Depends(_read)
) -> ClientOut:
    return ClientOut.model_validate(catalog_service.get(db, Client, item_id))


@router.patch("/clients/{item_id}", response_model=ClientOut)
def update_client(
    item_id: int,
    payload: ClientUpdate,
    db: Session = Depends(get_db),
    actor: User = Depends(_manage),
) -> ClientOut:
    return ClientOut.model_validate(
        catalog_service.update_client(db, item_id, payload, actor=actor)
    )


# Sites -----------------------------------------------------------------------


@router.get("/sites", response_model=Page[SiteOut])
def list_sites(
    search: str | None = None,
    active: bool | None = None,
    page: int = _PAGE,
    page_size: int = _PAGE_SIZE,
    db: Session = Depends(get_db),
    _actor: User = Depends(_read),
) -> Page[SiteOut]:
    items, total = catalog_service.list_items(
        db, Site, search_fields=[Site.name], order_by=Site.name,
        search=search, active=active, page=page, page_size=page_size,
    )
    return Page[SiteOut](items=[SiteOut.model_validate(i) for i in items], total=total)


@router.post("/sites", response_model=SiteOut, status_code=201)
def create_site(
    payload: SiteCreate, db: Session = Depends(get_db), actor: User = Depends(_manage)
) -> SiteOut:
    return SiteOut.model_validate(catalog_service.create_site(db, payload, actor=actor))


@router.get("/sites/{item_id}", response_model=SiteOut)
def get_site(
    item_id: int, db: Session = Depends(get_db), _actor: User = Depends(_read)
) -> SiteOut:
    return SiteOut.model_validate(catalog_service.get(db, Site, item_id))


@router.patch("/sites/{item_id}", response_model=SiteOut)
def update_site(
    item_id: int,
    payload: SiteUpdate,
    db: Session = Depends(get_db),
    actor: User = Depends(_manage),
) -> SiteOut:
    return SiteOut.model_validate(catalog_service.update_site(db, item_id, payload, actor=actor))


# Machines --------------------------------------------------------------------


@router.get("/machines", response_model=Page[MachineOut])
def list_machines(
    search: str | None = None,
    active: bool | None = None,
    page: int = _PAGE,
    page_size: int = _PAGE_SIZE,
    db: Session = Depends(get_db),
    _actor: User = Depends(_read),
) -> Page[MachineOut]:
    items, total = catalog_service.list_items(
        db, Machine, search_fields=[Machine.code, Machine.name], order_by=Machine.code,
        search=search, active=active, page=page, page_size=page_size,
    )
    return Page[MachineOut](items=[MachineOut.from_model(m) for m in items], total=total)


@router.post("/machines", response_model=MachineWithKeyOut, status_code=201)
def create_machine(
    payload: MachineCreate, db: Session = Depends(get_db), actor: User = Depends(_manage)
) -> MachineWithKeyOut:
    machine, key = machine_service.create_machine(db, payload, actor=actor)
    return MachineWithKeyOut(machine=MachineOut.from_model(machine), api_key=key)


@router.get("/machines/{item_id}", response_model=MachineOut)
def get_machine(
    item_id: int, db: Session = Depends(get_db), _actor: User = Depends(_read)
) -> MachineOut:
    return MachineOut.from_model(catalog_service.get(db, Machine, item_id))


@router.patch("/machines/{item_id}", response_model=MachineOut)
def update_machine(
    item_id: int,
    payload: MachineUpdate,
    db: Session = Depends(get_db),
    actor: User = Depends(_manage),
) -> MachineOut:
    return MachineOut.from_model(
        machine_service.update_machine(db, item_id, payload, actor=actor)
    )


@router.post("/machines/{item_id}/rotate-key", response_model=MachineWithKeyOut)
def rotate_machine_key(
    item_id: int, db: Session = Depends(get_db), actor: User = Depends(_manage)
) -> MachineWithKeyOut:
    machine, key = machine_service.rotate_key(db, item_id, actor=actor)
    return MachineWithKeyOut(machine=MachineOut.from_model(machine), api_key=key)
