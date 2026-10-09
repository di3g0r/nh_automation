"""Key/value settings store. Defaults live in code and are seeded on first access."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models.settings import Setting

DEFAULTS: dict[str, Any] = {
    "default_site_id": None,
    "approver_must_differ": False,
    "plc_offline_seconds": 60,
    "session_timeout_office_hours": 8,
    "session_timeout_operator_hours": 12,
    "difference_tolerance_liters": 0,
}


def ensure_defaults(db: Session) -> None:
    existing = {s.key for s in db.query(Setting.key).all()}
    for key, value in DEFAULTS.items():
        if key not in existing:
            db.add(Setting(key=key, value=value))
    db.commit()


def get_value(db: Session, key: str) -> Any:
    row = db.query(Setting).filter(Setting.key == key).first()
    if row is not None:
        return row.value
    if key in DEFAULTS:
        return DEFAULTS[key]
    raise KeyError(key)


def list_all(db: Session) -> list[Setting]:
    ensure_defaults(db)
    return db.query(Setting).order_by(Setting.key).all()


def set_value_no_commit(db: Session, key: str, value: Any) -> None:
    """Write a setting inside the caller's transaction (used to keep derived
    settings such as `default_site_id` in sync with catalog changes)."""
    row = db.query(Setting).filter(Setting.key == key).first()
    if row is None:
        db.add(Setting(key=key, value=value))
    else:
        row.value = value
    db.flush()


# Derived from catalogs; changed only through their own services.
READ_ONLY_KEYS = {"default_site_id"}


def update_value(db: Session, key: str, value: Any) -> Setting:
    if key in READ_ONLY_KEYS:
        raise AppError(
            "READ_ONLY_SETTING",
            "Este parámetro se cambia desde Catálogos > Sitios (sitio por defecto).",
            409,
        )
    row = db.query(Setting).filter(Setting.key == key).first()
    if row is None:
        if key not in DEFAULTS:
            raise KeyError(key)
        row = Setting(key=key, value=value)
        db.add(row)
    else:
        row.value = value
    db.commit()
    db.refresh(row)
    return row
