"""Key/value settings store. Defaults live in code and are seeded on first access."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models.settings import Setting

DEFAULTS: dict[str, Any] = {
    "default_site_id": None,
    "plc_offline_seconds": 60,
    "session_timeout_office_hours": 8,
    "session_timeout_operator_hours": 12,
    # TODO(OPEN-19): acceptable difference range (BR-12); within range if
    # |difference| <= liters OR <= percent of the ordered liters.
    "difference_tolerance_liters": 0,
    "difference_tolerance_percent": 0,
}

# key -> (min, max or None, Spanish label) for decimal settings with 2 decimals.
_DECIMAL_RANGES: dict[str, tuple[Decimal, Decimal | None, str]] = {
    "difference_tolerance_liters": (Decimal("0"), None, "La tolerancia de diferencia (L)"),
    "difference_tolerance_percent": (
        Decimal("0"), Decimal("100"), "La tolerancia de diferencia (%)"
    ),
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


def _invalid(message: str) -> AppError:
    return AppError("INVALID_SETTING", message, 422)


def _validate(key: str, value: Any) -> Any:
    if key not in _DECIMAL_RANGES:
        return value
    low, high, label = _DECIMAL_RANGES[key]
    if isinstance(value, bool) or not isinstance(value, int | float | str):
        raise _invalid(f"{label} debe ser un número.")
    try:
        number = Decimal(str(value).strip())
    except InvalidOperation as exc:
        raise _invalid(f"{label} debe ser un número.") from exc
    if not number.is_finite():
        raise _invalid(f"{label} debe ser un número.")
    if number != number.quantize(Decimal("0.01")):
        raise _invalid(f"{label} admite máximo 2 decimales.")
    if number < low or (high is not None and number > high):
        bound = f"entre {low} y {high}" if high is not None else f"mayor o igual a {low}"
        raise _invalid(f"{label} debe ser {bound}.")
    # JSON number; integral values stay ints ("5" -> 5, "2.50" -> 2.5).
    return int(number) if number == number.to_integral_value() else float(number)


def update_value(db: Session, key: str, value: Any) -> Setting:
    if key in READ_ONLY_KEYS:
        raise AppError(
            "READ_ONLY_SETTING",
            "Este parámetro se cambia desde Catálogos > Sitios (sitio por defecto).",
            409,
        )
    row = db.query(Setting).filter(Setting.key == key).first()
    if row is None and key not in DEFAULTS:
        raise KeyError(key)
    value = _validate(key, value)
    if row is None:
        row = Setting(key=key, value=value)
        db.add(row)
    else:
        row.value = value
    db.commit()
    db.refresh(row)
    return row
