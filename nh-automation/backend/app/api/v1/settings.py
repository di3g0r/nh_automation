"""Settings endpoints. Permission: settings.manage."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_permission
from app.core.errors import not_found
from app.core.permissions import Permission
from app.models.user import User
from app.schemas.settings import SettingOut, SettingUpdate
from app.services import settings_service

router = APIRouter(prefix="/settings", tags=["settings"])

_manage = require_permission(Permission.SETTINGS_MANAGE)


@router.get("", response_model=list[SettingOut])
def list_settings(
    db: Session = Depends(get_db), _actor: User = Depends(_manage)
) -> list[SettingOut]:
    rows = settings_service.list_all(db)
    return [SettingOut(key=r.key, value=r.value) for r in rows]


@router.patch("/{key}", response_model=SettingOut)
def update_setting(
    key: str,
    payload: SettingUpdate,
    db: Session = Depends(get_db),
    _actor: User = Depends(_manage),
) -> SettingOut:
    try:
        row = settings_service.update_value(db, key, payload.value)
    except KeyError as exc:
        raise not_found("Parámetro de configuración") from exc
    return SettingOut(key=row.key, value=row.value)
