"""User management endpoints (FR-USR). Permission: users.manage."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_permission
from app.core.permissions import Permission
from app.models.user import User
from app.schemas.common import Page
from app.schemas.user import ResetCredentials, UserCreate, UserOut, UserUpdate
from app.services import user_service

router = APIRouter(prefix="/users", tags=["users"])

_manage = require_permission(Permission.USERS_MANAGE)


@router.get("", response_model=Page[UserOut])
def list_users(
    search: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    _actor: User = Depends(_manage),
) -> Page[UserOut]:
    items, total = user_service.list_users(db, search=search, page=page, page_size=page_size)
    return Page[UserOut](items=[UserOut.from_model(u) for u in items], total=total)


@router.post("", response_model=UserOut, status_code=201)
def create_user(
    payload: UserCreate, db: Session = Depends(get_db), actor: User = Depends(_manage)
) -> UserOut:
    user = user_service.create_user(db, payload, actor=actor)
    return UserOut.from_model(user)


@router.get("/{user_id}", response_model=UserOut)
def get_user(
    user_id: int, db: Session = Depends(get_db), _actor: User = Depends(_manage)
) -> UserOut:
    return UserOut.from_model(user_service.get_by_id(db, user_id))


@router.patch("/{user_id}", response_model=UserOut)
def update_user(
    user_id: int,
    payload: UserUpdate,
    db: Session = Depends(get_db),
    actor: User = Depends(_manage),
) -> UserOut:
    user = user_service.update_user(db, user_id, payload, actor=actor)
    return UserOut.from_model(user)


@router.post("/{user_id}/deactivate", response_model=UserOut)
def deactivate_user(
    user_id: int, db: Session = Depends(get_db), actor: User = Depends(_manage)
) -> UserOut:
    user = user_service.set_active(db, user_id, active=False, actor=actor)
    return UserOut.from_model(user)


@router.post("/{user_id}/activate", response_model=UserOut)
def activate_user(
    user_id: int, db: Session = Depends(get_db), actor: User = Depends(_manage)
) -> UserOut:
    user = user_service.set_active(db, user_id, active=True, actor=actor)
    return UserOut.from_model(user)


@router.post("/{user_id}/reset-credentials", response_model=UserOut)
def reset_credentials(
    user_id: int,
    payload: ResetCredentials,
    db: Session = Depends(get_db),
    actor: User = Depends(_manage),
) -> UserOut:
    user = user_service.reset_credentials(db, user_id, payload, actor=actor)
    return UserOut.from_model(user)
