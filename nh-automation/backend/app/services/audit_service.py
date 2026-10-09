"""Generic audit service (FR-AUD), used by every later phase (BR-18).

Usage: audit.record(db, user=current_user, entity="user", entity_id=5,
                     action="update", before={...}, after={...})
`user` may be None for system/PLC actions (data model §2).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog
from app.models.user import User


def record(
    db: Session,
    *,
    user: User | None,
    entity: str,
    entity_id: int | None,
    action: str,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
) -> AuditLog:
    entry = AuditLog(
        user_id=user.id if user else None,
        entity=entity,
        entity_id=entity_id,
        action=action,
        before=before,
        after=after,
    )
    db.add(entry)
    db.flush()
    return entry


def list_entries(
    db: Session,
    *,
    user_id: int | None = None,
    entity: str | None = None,
    date_from=None,
    date_to=None,
    page: int = 1,
    page_size: int = 50,
) -> tuple[list[AuditLog], int]:
    query = db.query(AuditLog)
    if user_id is not None:
        query = query.filter(AuditLog.user_id == user_id)
    if entity is not None:
        query = query.filter(AuditLog.entity == entity)
    if date_from is not None:
        query = query.filter(AuditLog.created_at >= date_from)
    if date_to is not None:
        query = query.filter(AuditLog.created_at <= date_to)

    total = query.count()
    items = (
        query.order_by(AuditLog.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return items, total
