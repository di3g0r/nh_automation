"""Shared FastAPI dependencies: DB session, current user, permission checks, CSRF."""

from __future__ import annotations

from collections.abc import Callable

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError, unauthorized
from app.core.permissions import Permission, role_has_permission
from app.core.security import constant_time_eq
from app.db.session import get_db
from app.models.session import UserSession
from app.models.user import User
from app.services import auth_service

STATE_CHANGING_METHODS = {"POST", "PATCH", "PUT", "DELETE"}

__all__ = ["get_db"]


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    """Resolve the session cookie into a User, enforcing CSRF on state-changing requests."""
    settings = get_settings()
    token = request.cookies.get(settings.session_cookie_name)
    if not token:
        raise unauthorized()

    session: UserSession | None = auth_service.get_active_session(db, token)
    if session is None:
        raise unauthorized()

    user = db.get(User, session.user_id)
    if user is None or not user.is_active:
        raise unauthorized()

    if request.method in STATE_CHANGING_METHODS:
        csrf_header = request.headers.get("X-CSRF-Token")
        if not csrf_header or not constant_time_eq(csrf_header, session.csrf_token):
            raise AppError("CSRF_INVALID", "Token CSRF inválido o ausente.", 403)

    auth_service.touch_session(db, session, user)
    request.state.session = session
    request.state.user = user
    return user


def require_permission(permission: Permission) -> Callable[..., User]:
    """Dependency factory: `Depends(require_permission(Permission.USERS_MANAGE))`."""

    def checker(user: User = Depends(get_current_user)) -> User:
        if not role_has_permission(user.role, permission):
            raise AppError(
                "FORBIDDEN", "No tiene permiso para realizar esta acción.", 403
            )
        return user

    return checker
