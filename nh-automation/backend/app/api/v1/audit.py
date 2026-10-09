"""Read-only audit log listing (FR-AUD-2). Permission: audit.view."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_permission
from app.core.permissions import Permission
from app.models.user import User
from app.schemas.audit import AuditLogOut
from app.schemas.common import Page
from app.services import audit_service

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("", response_model=Page[AuditLogOut])
def list_audit(
    user_id: int | None = None,
    entity: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    _actor: User = Depends(require_permission(Permission.AUDIT_VIEW)),
) -> Page[AuditLogOut]:
    items, total = audit_service.list_entries(
        db,
        user_id=user_id,
        entity=entity,
        date_from=date_from,
        date_to=date_to,
        page=page,
        page_size=page_size,
    )
    return Page[AuditLogOut](
        items=[AuditLogOut.model_validate(i) for i in items], total=total
    )
