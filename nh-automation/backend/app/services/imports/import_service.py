"""Catalog import: source -> column mapping -> per-row validation -> preview / confirm (FR-CAT-7).

Preview and confirm run the exact same validation. Confirm re-reads the source
and saves only when there are zero errors -- all rows in one transaction, so a
file (or query) with any error saves nothing.

Modes:
- `create_only`: new codes are created; existing codes are skipped (warning).
- `upsert`: new codes are created; existing codes are updated with the
  non-empty values from the source (is_active is never changed by an import).

Initial stock (optional column) is written as a `receipt` movement at the
default site with note "Importación inicial", only for items without any
movement at that site yet -- so re-running an import never doubles stock.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any, Literal, cast

from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models.catalogs import PackagingItem, Product
from app.models.user import User
from app.services import audit_service, stock_service
from app.services.catalog_service import _META, get_default_site, snapshot
from app.services.imports.columns import (
    CATEGORY_ALIASES,
    FIELDS,
    FieldSpec,
    ImportKind,
    map_columns,
    normalize_header,
)
from app.services.imports.sources import SourceData, SourceInput, get_source
from app.services.stock_service import ItemRef

ImportMode = Literal["create_only", "upsert"]
RowAction = Literal["create", "update", "skip", "error"]
INITIAL_STOCK_NOTE = "Importación inicial"

_THOUSANDS = re.compile(r"^-?\d{1,3}(,\d{3})+(\.\d+)?$")


@dataclass
class RowResult:
    row_number: int
    values: dict[str, Any]
    action: RowAction = "create"
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    apply_initial_stock: bool = False


@dataclass
class ImportResult:
    kind: ImportKind
    source: str
    mode: ImportMode
    columns: dict[str, str]  # source column -> canonical field
    unknown_columns: list[str]
    missing_columns: list[str]  # required canonical fields not found (labels)
    global_errors: list[str]
    rows: list[RowResult]

    @property
    def summary(self) -> dict[str, int]:
        counts = {"total": len(self.rows), "create": 0, "update": 0, "skip": 0, "error": 0}
        for r in self.rows:
            counts[r.action] += 1
        counts["initial_stock"] = sum(1 for r in self.rows if r.apply_initial_stock)
        return counts

    @property
    def has_errors(self) -> bool:
        return bool(self.global_errors) or any(r.action == "error" for r in self.rows)


_MODEL: dict[ImportKind, type[Product | PackagingItem]] = {
    "products": Product,
    "packaging-items": PackagingItem,
}
_ITEM_TYPE: dict[ImportKind, stock_service.ItemType] = {
    "products": "product",
    "packaging-items": "packaging",
}


def _existing_by_code(
    db: Session, model: type[Product | PackagingItem]
) -> dict[str, Product | PackagingItem]:
    items = cast(list[Product | PackagingItem], db.query(model).all())
    return {obj.code: obj for obj in items}


# Value parsing -----------------------------------------------------------------


def _as_text(raw: Any) -> str:
    if raw is None:
        return ""
    if isinstance(raw, float) and raw.is_integer():
        raw = int(raw)  # XLSX/DB numeric codes: 1001.0 -> "1001"
    return str(raw).strip()


def _as_decimal(raw: Any) -> Decimal:
    if isinstance(raw, bool):
        raise InvalidOperation
    if isinstance(raw, int | Decimal):
        return Decimal(raw)
    if isinstance(raw, float):
        return Decimal(str(raw))
    text = _as_text(raw).replace(" ", "")
    if _THOUSANDS.match(text):
        text = text.replace(",", "")
    value = Decimal(text)
    if not value.is_finite():
        raise InvalidOperation
    return value


def _parse(spec: FieldSpec, raw: Any, errors: list[str]) -> Any:
    """Return the parsed value, or None when empty. Appends Spanish errors."""
    if _as_text(raw) == "":
        if spec.required:
            errors.append(f"{spec.label}: campo obligatorio.")
        return None

    if spec.kind == "text":
        value = _as_text(raw)
        if spec.max_length and len(value) > spec.max_length:
            errors.append(f"{spec.label}: máximo {spec.max_length} caracteres.")
        return value

    if spec.kind == "category":
        category = CATEGORY_ALIASES.get(normalize_header(raw))
        if category is None:
            errors.append(
                f"{spec.label}: '{_as_text(raw)}' no es válida "
                "(envase, caja, bolsa, etiqueta, otro)."
            )
        return category

    try:
        number = _as_decimal(raw)
    except (InvalidOperation, ValueError):
        errors.append(f"{spec.label}: '{_as_text(raw)}' no es un número válido.")
        return None
    if number < 0:
        errors.append(f"{spec.label}: no puede ser negativo.")
        return None
    if spec.kind == "int":
        if number != number.to_integral_value():
            errors.append(f"{spec.label}: debe ser un número entero.")
            return None
        return int(number)
    if spec.name == "container_liters" and number == 0:
        errors.append(f"{spec.label}: debe ser mayor que cero.")
        return None
    if number != number.quantize(Decimal("0.01")):
        errors.append(f"{spec.label}: máximo 2 decimales.")
        return None
    return number.quantize(Decimal("0.01"))


# Validation --------------------------------------------------------------------


def _validate(
    db: Session, kind: ImportKind, mode: ImportMode, data: SourceData, source: str
) -> ImportResult:
    specs = FIELDS[kind]
    mapping, unknown = map_columns(kind, data.columns)
    present = set(mapping.values())
    missing = [s.label for s in specs if s.required and s.name not in present]
    global_errors: list[str] = []
    if missing:
        global_errors.append("Faltan columnas obligatorias: " + ", ".join(missing) + ".")
    if not data.rows:
        global_errors.append("No hay filas para importar.")

    model = _MODEL[kind]
    item_type = _ITEM_TYPE[kind]
    existing = _existing_by_code(db, model)
    default_site = get_default_site(db)
    seen: dict[str, int] = {}
    rows: list[RowResult] = []

    for number, raw_row in data.rows:
        canonical = {mapping[c]: v for c, v in raw_row.items() if c in mapping}
        errors: list[str] = []
        values = {s.name: _parse(s, canonical.get(s.name), errors) for s in specs}
        result = RowResult(row_number=number, values=values, errors=errors)

        code = values.get("code")
        if code:
            if code in seen:
                errors.append(f"Código duplicado en el origen (también en la fila {seen[code]}).")
            else:
                seen[code] = number

        stock = values.get("initial_stock")
        if stock is not None and kind == "packaging-items" and stock != stock.to_integral_value():
            errors.append("Existencia inicial: los materiales se registran en unidades enteras.")

        if errors:
            result.action = "error"
            rows.append(result)
            continue

        current = existing.get(code) if code else None
        if current is None:
            result.action = "create"
        elif mode == "create_only":
            result.action = "skip"
            result.warnings.append("El código ya existe; se omitirá (modo: solo crear nuevos).")
        else:
            changes = _changes(current, values)
            result.action = "update" if changes else "skip"
            if not changes:
                result.warnings.append("Sin cambios.")

        if stock:  # None or 0 -> nothing to do
            if default_site is None:
                result.errors.append("No hay sitio por defecto para la existencia inicial.")
                result.action = "error"
            elif current is not None and stock_service.has_movements(
                db, default_site.id, ItemRef(item_type, current.id)
            ):
                result.warnings.append(
                    "Existencia inicial ignorada: el artículo ya tiene movimientos de inventario."
                )
            elif not (result.action == "skip" and mode == "create_only"):
                result.apply_initial_stock = True

        rows.append(result)

    return ImportResult(
        kind=kind,
        source=source,
        mode=mode,
        columns=mapping,
        unknown_columns=unknown,
        missing_columns=missing,
        global_errors=global_errors,
        rows=rows,
    )


def _changes(obj: Product | PackagingItem, values: dict[str, Any]) -> dict[str, Any]:
    """Fields whose non-empty source value differs from the stored one."""
    out: dict[str, Any] = {}
    for key, value in values.items():
        if key in ("code", "initial_stock") or value is None:
            continue
        current = getattr(obj, key)
        if isinstance(current, Decimal) or isinstance(value, Decimal):
            if current is not None and Decimal(current) == Decimal(value):
                continue
        elif current == value:
            continue
        out[key] = value
    return out


# Public API --------------------------------------------------------------------


def _check_mode(mode: str) -> ImportMode:
    if mode not in ("create_only", "upsert"):
        raise AppError("IMPORT_INVALID_MODE", "Modo de importación inválido.", 422)
    return mode  # type: ignore[return-value]


def preview(
    db: Session, kind: ImportKind, *, source: str, mode: str, data: SourceInput
) -> ImportResult:
    checked_mode = _check_mode(mode)
    raw = get_source(source).read(kind, data)
    return _validate(db, kind, checked_mode, raw, source)


def confirm(
    db: Session, kind: ImportKind, *, source: str, mode: str, data: SourceInput, actor: User
) -> ImportResult:
    result = preview(db, kind, source=source, mode=mode, data=data)
    if result.has_errors:
        raise AppError(
            "IMPORT_HAS_ERRORS",
            "La importación tiene errores; no se guardó nada. "
            "Corrija el origen e intente de nuevo.",
            422,
            {"summary": result.summary, "global_errors": result.global_errors},
        )

    model = _MODEL[kind]
    item_type = _ITEM_TYPE[kind]
    _, entity, fields = _META[model]
    existing = _existing_by_code(db, model)
    default_site = get_default_site(db)

    try:
        for row in result.rows:
            values = {k: v for k, v in row.values.items() if k != "initial_stock"}
            obj = existing.get(values["code"])
            if row.action == "create":
                obj = model(**{k: v for k, v in values.items() if v is not None}, is_active=True)
                db.add(obj)
                db.flush()
                audit_service.record(
                    db, user=actor, entity=entity, entity_id=obj.id, action="create",
                    before=None, after=snapshot(obj, fields) | {"via": f"import:{source}"},
                )
            elif row.action == "update" and obj is not None:
                before = snapshot(obj, fields)
                for key, value in _changes(obj, values).items():
                    setattr(obj, key, value)
                db.flush()
                audit_service.record(
                    db, user=actor, entity=entity, entity_id=obj.id, action="update",
                    before=before, after=snapshot(obj, fields) | {"via": f"import:{source}"},
                )

            if row.apply_initial_stock and obj is not None and default_site is not None:
                movement = stock_service.apply_movement(
                    db, site_id=default_site.id, item=ItemRef(item_type, obj.id),
                    movement_type="receipt", quantity=row.values["initial_stock"],
                    user=actor, note=INITIAL_STOCK_NOTE,
                )
                audit_service.record(
                    db, user=actor, entity="stock", entity_id=movement.id, action="receipt",
                    before=None,
                    after={"quantity": str(movement.quantity), "note": INITIAL_STOCK_NOTE,
                           "site_id": default_site.id, f"{item_type}_id": obj.id},
                )

        audit_service.record(
            db, user=actor, entity="import", entity_id=None, action=f"import_{kind}",
            before=None, after={"source": source, "mode": mode, "summary": result.summary},
        )
        db.commit()
    except Exception:
        db.rollback()
        raise
    return result
