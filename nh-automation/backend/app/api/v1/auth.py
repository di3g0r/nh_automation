"""Authentication endpoints: password login, PIN login, logout, me, change-password."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.core.config import get_settings
from app.core.errors import AppError
from app.core.permissions import permissions_for_role
from app.models.session import UserSession
from app.models.user import User
from app.schemas.auth import ChangePassword, MeOut, PasswordLogin, PinLogin
from app.schemas.user import UserOut
from app.services import auth_service, user_service

router = APIRouter(prefix="/auth", tags=["auth"])


def _set_session_cookies(response: Response, raw_token: str, csrf_token: str) -> None:
    settings = get_settings()
    secure = settings.is_production
    response.set_cookie(
        settings.session_cookie_name,
        raw_token,
        httponly=True,
        secure=secure,
        samesite="lax",
        path="/",
    )
    # Double-submit CSRF cookie: readable by the frontend JS, mirrored back as
    # the X-CSRF-Token header on state-changing requests (see app/api/deps.py).
    response.set_cookie(
        settings.csrf_cookie_name,
        csrf_token,
        httponly=False,
        secure=secure,
        samesite="lax",
        path="/",
    )


def _clear_session_cookies(response: Response) -> None:
    settings = get_settings()
    response.delete_cookie(settings.session_cookie_name, path="/")
    response.delete_cookie(settings.csrf_cookie_name, path="/")


@router.post("/login", response_model=UserOut)
def login(
    payload: PasswordLogin, request: Request, response: Response, db: Session = Depends(get_db)
) -> UserOut:
    user = auth_service.authenticate_password(db, payload.username, payload.password)
    session, raw_token, csrf_token = auth_service.create_session(
        db, user, user_agent=request.headers.get("user-agent")
    )
    _set_session_cookies(response, raw_token, csrf_token)
    return UserOut.from_model(user)


@router.post("/pin-login", response_model=UserOut)
def pin_login(
    payload: PinLogin, request: Request, response: Response, db: Session = Depends(get_db)
) -> UserOut:
    user = auth_service.authenticate_pin(db, payload.username, payload.pin)
    session, raw_token, csrf_token = auth_service.create_session(
        db, user, user_agent=request.headers.get("user-agent")
    )
    _set_session_cookies(response, raw_token, csrf_token)
    return UserOut.from_model(user)


@router.post("/logout")
def logout(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    session: UserSession = request.state.session
    auth_service.revoke_session(db, session)
    _clear_session_cookies(response)
    return {"ok": True}


@router.get("/me", response_model=MeOut)
def me(user: User = Depends(get_current_user)) -> MeOut:
    return MeOut(
        id=user.id,
        username=user.username,
        full_name=user.full_name,
        role=user.role,
        permissions=sorted(p.value for p in permissions_for_role(user.role)),
    )


@router.post("/change-password", response_model=UserOut)
def change_password(
    payload: ChangePassword, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> UserOut:
    from app.core.security import verify_secret

    if not verify_secret(payload.current_password, user.password_hash):
        raise AppError("INVALID_CREDENTIALS", "La contraseña actual es incorrecta.", 401)
    if payload.new_password is None and payload.new_pin is None:
        raise AppError(
            "NO_CREDENTIALS_PROVIDED", "Debe proporcionar una nueva contraseña o PIN.", 422
        )
    updated = user_service.change_own_credentials(
        db, user, new_password=payload.new_password, new_pin=payload.new_pin
    )
    return UserOut.from_model(updated)
