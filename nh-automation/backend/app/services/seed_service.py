"""Seed data (data model §5).

The production seed (site, clients, packaging items) is applied by the phase-1
Alembic migration; `ensure_base_catalogs` is the idempotent equivalent used by
the test suite and the `seed-catalogs` CLI. `seed_dev` adds dev-only data.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.permissions import Role
from app.core.security import hash_secret, hash_token, new_token
from app.models.catalogs import Client, Machine, PackagingItem, Product, Site
from app.models.user import User
from app.services import settings_service

BASE_SITE = "ECOINDUSTRIAL PACÍFICO"
BASE_CLIENTS = [("NOBELTECH", "NB"), ("AGRONB", "ANB")]
BASE_PACKAGING = [
    ("ENVCO01005", "Envase 1 L liso Novapack", "envase"),
    ("ENVLI01004", "Envase 1 L corrugado", "envase"),
    ("ENVLI20001", "Envase 20 L Fisher", "envase"),
    ("ENVLI05003", "Envase 5 L Fisher", "envase"),
    ("ENVLI25007", "Envase 250 ml liso Novapack", "envase"),
    ("ENVCO25006", "Envase 250 ml corrugado", "envase"),
    ("BOLTE20008", "Bolsa termosellada 1 kg", "bolsa"),
    ("CAJ01FP007", "Caja Forcrop 12x1", "caja"),
    ("CAJ05FP006", "Caja Forcrop 4x5", "caja"),
    ("CAJ01BL003", "Caja blanca 12x1", "caja"),
    ("CAJ05BL004", "Caja blanca 4x5", "caja"),
    ("CAJ05BL005", "Caja blanca 0.250 grs", "caja"),
    ("CAJ01AZ002", "Caja azul 12x1", "caja"),
    ("CAJ05AZ001", "Caja azul 4x5", "caja"),
]

DEV_PRODUCTS = [
    ("GRN100C1XL20F004", "NB-NEEM", "GRN", "1X20", "20"),
    ("QVR200C1XL09M01", "BASE CALCIO", "QVR", "1000", "1000"),
    ("QVR200C1XL20F003", "NH-CALCIO", "QVR", "1X20", "20"),
]
DEV_USERS = [
    ("director", "Director (dev)", Role.MASTER_ADMIN),
    ("oficina", "Oficina (dev)", Role.ADMIN),
    ("bodega", "Supervisor de bodega (dev)", Role.SUPERVISOR),
    ("operador", "Operador (dev)", Role.OPERATOR),
]
DEV_PASSWORD = "cambiar-123"
DEV_PIN = "1234"


def ensure_base_catalogs(db: Session) -> Site:
    site = db.query(Site).filter(Site.name == BASE_SITE).first()
    if site is None:
        has_default = db.query(Site).filter(Site.is_default.is_(True)).first() is not None
        site = Site(name=BASE_SITE, is_default=not has_default, is_active=True)
        db.add(site)
        db.flush()
    for name, code in BASE_CLIENTS:
        if db.query(Client).filter(Client.code == code).first() is None:
            db.add(Client(name=name, code=code, is_active=True))
    for code, description, category in BASE_PACKAGING:
        if db.query(PackagingItem).filter(PackagingItem.code == code).first() is None:
            db.add(
                PackagingItem(
                    code=code, description=description, category=category,
                    low_stock_threshold=0, is_active=True,
                )
            )
    default = db.query(Site).filter(Site.is_default.is_(True)).first()
    settings_service.set_value_no_commit(db, "default_site_id", default.id if default else None)
    db.commit()
    return site


def seed_dev(db: Session) -> list[str]:
    """Dev-only data. Returns a log of what was created (idempotent)."""
    log: list[str] = []
    site = ensure_base_catalogs(db)
    for code, name, provider, presentation, liters in DEV_PRODUCTS:
        if db.query(Product).filter(Product.code == code).first() is None:
            db.add(
                Product(
                    code=code, name=name, provider=provider, presentation=presentation,
                    container_liters=Decimal(liters), is_active=True,
                )
            )
            log.append(f"producto {code}")
    for n in range(1, 7):
        code = f"M{n:02d}"
        if db.query(Machine).filter(Machine.code == code).first() is None:
            # Dev keys are random and not shown; rotate from the UI to get one.
            db.add(
                Machine(
                    code=code, name=f"Máquina {n}", site_id=site.id, is_active=True,
                    in_maintenance=False, api_key_hash=hash_token(new_token()),
                )
            )
            log.append(f"máquina {code}")
    for username, full_name, role in DEV_USERS:
        if db.query(User).filter(User.username == username).first() is None:
            db.add(
                User(
                    username=username, full_name=full_name, role=role.value,
                    password_hash=hash_secret(DEV_PASSWORD),
                    pin_hash=hash_secret(DEV_PIN) if role == Role.OPERATOR else None,
                    is_active=True,
                )
            )
            log.append(f"usuario {username}")
    db.commit()
    return log
