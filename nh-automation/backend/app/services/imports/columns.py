"""Canonical import fields and the column-name aliases that map onto them.

Every import source (file, external database, future adapters) produces rows
keyed by whatever column names it has; `map_columns` translates them to the
canonical field names below. To support a new spreadsheet layout or external
schema, either add an alias here or alias the column in the source query
(`SELECT clave AS codigo ...`).
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Literal

ImportKind = Literal["products", "packaging-items"]
FieldKind = Literal["text", "decimal", "int", "category"]


@dataclass(frozen=True)
class FieldSpec:
    name: str
    label: str  # Spanish, used in error messages and preview headers
    kind: FieldKind
    required: bool
    aliases: tuple[str, ...]
    max_length: int | None = None


INITIAL_STOCK = FieldSpec(
    "initial_stock",
    "Existencia inicial",
    "decimal",
    False,
    ("existencia_inicial", "initial_stock", "existencia", "stock", "inventario", "on_hand"),
)

FIELDS: dict[ImportKind, tuple[FieldSpec, ...]] = {
    "products": (
        FieldSpec("code", "Código", "text", True, ("codigo", "code", "clave", "sku"), 64),
        FieldSpec("name", "Nombre", "text", True, ("nombre", "name", "producto"), 200),
        FieldSpec("provider", "Proveedor", "text", True, ("proveedor", "provider"), 200),
        FieldSpec(
            "presentation", "Presentación", "text", True, ("presentacion", "presentation"), 64
        ),
        FieldSpec(
            "container_liters",
            "Litros por envase",
            "decimal",
            False,
            ("litros_por_envase", "litros_envase", "container_liters", "capacidad_litros"),
        ),
        INITIAL_STOCK,
    ),
    "packaging-items": (
        FieldSpec("code", "Código", "text", True, ("codigo", "code", "clave", "sku"), 64),
        FieldSpec(
            "description",
            "Descripción",
            "text",
            True,
            ("descripcion", "description", "nombre", "articulo"),
            200,
        ),
        FieldSpec("category", "Categoría", "category", True, ("categoria", "category", "tipo")),
        FieldSpec(
            "low_stock_threshold",
            "Umbral de stock bajo",
            "int",
            False,
            ("umbral_stock_bajo", "umbral", "stock_minimo", "minimo", "low_stock_threshold"),
        ),
        INITIAL_STOCK,
    ),
}

CATEGORY_ALIASES = {
    "envase": "envase",
    "envases": "envase",
    "caja": "caja",
    "cajas": "caja",
    "bolsa": "bolsa",
    "bolsas": "bolsa",
    "etiqueta": "etiqueta",
    "etiquetas": "etiqueta",
    "otro": "otro",
    "otros": "otro",
}


def normalize_header(raw: object) -> str:
    """'Código ' -> 'codigo'; 'Litros por envase' -> 'litros_por_envase'."""
    text = unicodedata.normalize("NFKD", str(raw or "")).encode("ascii", "ignore").decode()
    text = re.sub(r"[^a-z0-9]+", "_", text.strip().lower())
    return text.strip("_")


def map_columns(kind: ImportKind, columns: list[str]) -> tuple[dict[str, str], list[str]]:
    """Return ({source column -> canonical field}, unknown source columns).

    The first source column matching a field wins; later duplicates are unknown.
    """
    alias_to_field = {alias: f.name for f in FIELDS[kind] for alias in f.aliases}
    mapping: dict[str, str] = {}
    unknown: list[str] = []
    taken: set[str] = set()
    for col in columns:
        field = alias_to_field.get(normalize_header(col))
        if field is None or field in taken:
            unknown.append(col)
            continue
        mapping[col] = field
        taken.add(field)
    return mapping, unknown
