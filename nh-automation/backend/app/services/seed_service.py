"""Seed data (data model §5).

The production seed (site, razones sociales, order sequences, packaging items)
is applied by the phase-1/1b Alembic migrations; `ensure_base_catalogs` is the
idempotent equivalent used by the test suite and the `seed-catalogs` CLI.
`seed_dev` adds dev-only data (sample products, clients, machines, users).
There are no production clients (NOBELTECH/AGRONB are razones sociales).
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.permissions import Role
from app.core.security import hash_secret, hash_token, new_token
from app.models.catalogs import Client, Machine, PackagingItem, Product, RazonSocial, Site
from app.models.user import User
from app.services import sequence_service, settings_service

BASE_SITE = "ECOINDUSTRIAL PACÍFICO"
# TODO(OPEN-16): RS3/RS4 are placeholders until the owner names them.
BASE_RAZONES_SOCIALES = [
    ("NB", "NOBELTECH"),
    ("ANB", "AGRONB"),
    ("RS3", "Razón social 3 (por definir)"),
    ("RS4", "Razón social 4 (por definir)"),
]
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

# code, name, provider, presentation, container liters, razón social code
DEV_PRODUCTS = [
    ("GRN100C1XL20F004", "NB-NEEM", "GRN", "1X20", "20", "NB"),
    ("QVR200C1XL09M01", "BASE CALCIO", "QVR", "1000", "1000", "ANB"),
    ("QVR200C1XL20F003", "NH-CALCIO", "QVR", "1X20", "20", "ANB"),
]
# Clearly fake sample clients (dev only).
DEV_CLIENTS = [
    ("Cliente de prueba Uno (dev)", "DEV1"),
    ("Cliente de prueba Dos (dev)", "DEV2"),
]
DEV_USERS = [
    ("director", "Director (dev)", Role.MASTER_ADMIN),
    ("oficina", "Oficina (dev)", Role.ADMIN),
    ("jefe", "Jefe de producción (dev)", Role.PRODUCTION_MANAGER),
]
DEV_PASSWORD = "cambiar-123"


def ensure_base_catalogs(db: Session) -> Site:
    site = db.query(Site).filter(Site.name == BASE_SITE).first()
    if site is None:
        has_default = db.query(Site).filter(Site.is_default.is_(True)).first() is not None
        site = Site(name=BASE_SITE, is_default=not has_default, is_active=True)
        db.add(site)
        db.flush()
    for code, name in BASE_RAZONES_SOCIALES:
        if db.query(RazonSocial).filter(RazonSocial.code == code).first() is None:
            db.add(RazonSocial(code=code, name=name, is_active=True))
    sequence_service.ensure_sequences(db)
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
    rs_by_code = {rs.code: rs for rs in db.query(RazonSocial).all()}
    for code, name, provider, presentation, liters, rs_code in DEV_PRODUCTS:
        rs = rs_by_code.get(rs_code)
        product = db.query(Product).filter(Product.code == code).first()
        if product is None:
            db.add(
                Product(
                    code=code, name=name, provider=provider, presentation=presentation,
                    container_liters=Decimal(liters), is_active=True,
                    razon_social_id=rs.id if rs else None,
                )
            )
            log.append(f"producto {code}")
        elif product.razon_social_id is None and rs is not None:
            product.razon_social_id = rs.id  # products seeded before phase 1b
            log.append(f"razón social {rs_code} en {code}")
    for name, code in DEV_CLIENTS:
        if db.query(Client).filter(Client.code == code).first() is None:
            db.add(Client(name=name, code=code, is_active=True))
            log.append(f"cliente {code}")
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
                    is_active=True,
                )
            )
            log.append(f"usuario {username}")
    db.commit()
    return log
