"""Import preview/confirm response schemas (FR-CAT-7)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from app.services.imports.columns import FIELDS, ImportKind
from app.services.imports.import_service import ImportResult


class ImportField(BaseModel):
    name: str
    label: str
    required: bool


class ImportRowOut(BaseModel):
    row_number: int
    values: dict[str, Any]
    action: str
    errors: list[str]
    warnings: list[str]
    apply_initial_stock: bool


class ImportResultOut(BaseModel):
    kind: str
    source: str
    mode: str
    fields: list[ImportField]
    columns: dict[str, str]
    unknown_columns: list[str]
    missing_columns: list[str]
    global_errors: list[str]
    summary: dict[str, int]
    has_errors: bool
    rows: list[ImportRowOut]

    @classmethod
    def from_result(cls, r: ImportResult) -> ImportResultOut:
        return cls(
            kind=r.kind,
            source=r.source,
            mode=r.mode,
            fields=[
                ImportField(name=f.name, label=f.label, required=f.required)
                for f in FIELDS[r.kind]
            ],
            columns=r.columns,
            unknown_columns=r.unknown_columns,
            missing_columns=r.missing_columns,
            global_errors=r.global_errors,
            summary=r.summary,
            has_errors=r.has_errors,
            rows=[
                ImportRowOut(
                    row_number=row.row_number,
                    values={k: (str(v) if v is not None and not isinstance(v, str | int) else v)
                            for k, v in row.values.items()},
                    action=row.action,
                    errors=row.errors,
                    warnings=row.warnings,
                    apply_initial_stock=row.apply_initial_stock,
                )
                for row in r.rows
            ],
        )


class ImportSourceOut(BaseModel):
    name: str
    label: str
    available: bool


class ImportSourcesOut(BaseModel):
    kind: ImportKind
    sources: list[ImportSourceOut]
