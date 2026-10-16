"""Catalog tables (data model §2, phases 1/1b): sites, clients, razones sociales,
products, packaging, machines.

Catalog rows are never hard-deleted (FR-CAT-6, NFR-6): they are deactivated
with `is_active = False` and keep displaying in older records.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

PACKAGING_CATEGORIES = ("envase", "caja", "bolsa", "etiqueta", "otro")


class Site(Base, TimestampMixin):
    __tablename__ = "sites"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    # Exactly one site is the default (FR-CAT-4); enforced in catalog_service.
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class Client(Base, TimestampMixin):
    __tablename__ = "clients"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class RazonSocial(Base, TimestampMixin):
    """Legal entity a product belongs to; its code is the operation-number suffix."""

    __tablename__ = "razones_sociales"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # Uppercase letters/digits, 1-6 chars (enforced in schemas).
    code: Mapped[str] = mapped_column(String(6), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class Product(Base, TimestampMixin):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # TODO(OPEN-5): code structure undecided; free text, unique.
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    provider: Mapped[str] = mapped_column(String(200), nullable=False)
    presentation: Mapped[str] = mapped_column(String(64), nullable=False)
    container_liters: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    # Nullable in the DB for imported rows; required by the product form (and,
    # from phase 2, to use the product in an order).
    razon_social_id: Mapped[int | None] = mapped_column(
        ForeignKey("razones_sociales.id"), nullable=True, index=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    razon_social: Mapped[RazonSocial | None] = relationship(lazy="joined")


class PackagingItem(Base, TimestampMixin):
    __tablename__ = "packaging_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    description: Mapped[str] = mapped_column(String(200), nullable=False)
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    low_stock_threshold: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class Machine(Base, TimestampMixin):
    __tablename__ = "machines"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    site_id: Mapped[int] = mapped_column(ForeignKey("sites.id"), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    in_maintenance: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # SHA-256 of the key; the plain key is shown once on creation/rotation (FR-CAT-5).
    # Phase-1 artifact, unused since phase 4 (PLCs log into PostgreSQL instead).
    api_key_hash: Mapped[str | None] = mapped_column(String(128), nullable=True, unique=True)
    # Phase 4: the machine's PostgreSQL login role (see plc_credentials_service).
    plc_db_username: Mapped[str | None] = mapped_column(String(63), nullable=True, unique=True)
    # Last PLC contact: set by the plc_events insert trigger (phase 4).
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    site: Mapped[Site] = relationship(lazy="joined")
