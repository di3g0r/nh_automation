"""Catalog import endpoints (FR-CAT-7). Permission: catalogs.manage.

Both preview and confirm take the same multipart form:
  source = "file" | "external_db"   mode = "create_only" | "upsert"   file = (for source=file)
Confirm re-reads the source and re-validates; it saves only with zero errors.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_permission
from app.core.permissions import Permission
from app.models.user import User
from app.schemas.imports import ImportResultOut, ImportSourceOut, ImportSourcesOut
from app.services.imports import import_service
from app.services.imports.sources import MAX_FILE_BYTES, SourceInput, list_sources

router = APIRouter(prefix="/imports", tags=["imports"])

_manage = require_permission(Permission.CATALOGS_MANAGE)

Kind = Literal["products", "packaging-items"]


async def _input(file: UploadFile | None) -> SourceInput:
    if file is None:
        return SourceInput()
    # Read one byte past the limit so FileSource can reject oversize uploads.
    content = await file.read(MAX_FILE_BYTES + 1)
    return SourceInput(filename=file.filename, content=content)


@router.get("/{kind}/sources", response_model=ImportSourcesOut)
def get_sources(kind: Kind, _actor: User = Depends(_manage)) -> ImportSourcesOut:
    return ImportSourcesOut(
        kind=kind, sources=[ImportSourceOut(**s) for s in list_sources(kind)]
    )


@router.post("/{kind}/preview", response_model=ImportResultOut)
async def preview_import(
    kind: Kind,
    source: str = Form("file"),
    mode: str = Form("create_only"),
    file: UploadFile | None = File(None),
    db: Session = Depends(get_db),
    _actor: User = Depends(_manage),
) -> ImportResultOut:
    data = await _input(file)
    result = import_service.preview(db, kind, source=source, mode=mode, data=data)
    return ImportResultOut.from_result(result)


@router.post("/{kind}/confirm", response_model=ImportResultOut)
async def confirm_import(
    kind: Kind,
    source: str = Form("file"),
    mode: str = Form("create_only"),
    file: UploadFile | None = File(None),
    db: Session = Depends(get_db),
    actor: User = Depends(_manage),
) -> ImportResultOut:
    data = await _input(file)
    result = import_service.confirm(db, kind, source=source, mode=mode, data=data, actor=actor)
    return ImportResultOut.from_result(result)
