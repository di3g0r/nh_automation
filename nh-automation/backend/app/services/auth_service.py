"""Login (password + PIN), lockout, and server-side session management.

FR-AUTH-1 password login, FR-AUTH-2 operator PIN login, FR-AUTH-3 sessions
with inactivity timeout (from settings), FR-AUTH-4 lockout after 5 failed
attempts for 15 minutes.
"""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.security import hash_token, new_token, verify_secret
from app.core.timezone import ensure_aware, utc_now
from app.models.session import UserSession
from app.models.user import User
from app.services import settings_service

MAX_FAILED_ATTEMPTS = 5
LOCKOUT_MINUTES = 15


def _is_locked(user: User) -> bool:
    return user.locked_until is not None and ensure_aware(user.locked_until) > utc_now()


def _register_failure(db: Session, user: User) -> None:
    user.failed_attempts += 1
    if user.failed_attempts >= MAX_FAILED_ATTEMPTS:
        user.locked_until = utc_now() + timedelta(minutes=LOCKOUT_MINUTES)
    db.commit()


def _register_success(db: Session, user: User) -> None:
    user.failed_attempts = 0
    user.locked_until = None
    user.last_login_at = utc_now()
    db.commit()


def _invalid_credentials_error() -> AppError:
    return AppError(
        "INVALID_CREDENTIALS", "Usuario o contraseña incorrectos.", 401
    )


def _check_account_usable(user: User | None) -> User:
    if user is None or not user.is_active:
        raise _invalid_credentials_error()
    if _is_locked(user):
        raise AppError(
            "ACCOUNT_LOCKED",
            "Cuenta bloqueada temporalmente por intentos fallidos. Intente de nuevo más tarde.",
            423,
        )
    return user


def authenticate_password(db: Session, username: str, password: str) -> User:
    from app.services.user_service import get_by_username

    user = get_by_username(db, username)
    user = _check_account_usable(user)

    if not verify_secret(password, user.password_hash):
        _register_failure(db, user)
        raise _invalid_credentials_error()

    _register_success(db, user)
    return user


def authenticate_pin(db: Session, username: str, pin: str) -> User:
    from app.services.user_service import get_by_username

    user = get_by_username(db, username)
    user = _check_account_usable(user)

    if not verify_secret(pin, user.pin_hash):
        _register_failure(db, user)
        raise AppError("INVALID_CREDENTIALS", "Usuario o PIN incorrectos.", 401)

    _register_success(db, user)
    return user


def _session_ttl_hours(db: Session, role: str) -> int:
    key = "session_timeout_operator_hours" if role == "operator" else "session_timeout_office_hours"
    return int(settings_service.get_value(db, key))


def create_session(
    db: Session, user: User, *, user_agent: str | None
) -> tuple[UserSession, str, str]:
    """Returns (session row, raw session token, raw csrf token)."""
    raw_token = new_token()
    csrf_token = new_token(16)
    ttl_hours = _session_ttl_hours(db, user.role)
    now = utc_now()
    session = UserSession(
        user_id=user.id,
        token_hash=hash_token(raw_token),
        csrf_token=csrf_token,
        user_agent=user_agent,
        expires_at=now + timedelta(hours=ttl_hours),
        last_seen_at=now,
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return session, raw_token, csrf_token


def get_active_session(db: Session, raw_token: str) -> UserSession | None:
    session = (
        db.query(UserSession).filter(UserSession.token_hash == hash_token(raw_token)).first()
    )
    if session is None or session.revoked_at is not None:
        return None
    if ensure_aware(session.expires_at) <= utc_now():
        return None
    return session


def touch_session(db: Session, session: UserSession, user: User) -> None:
    """Slide the inactivity window forward on each authenticated request."""
    now = utc_now()
    ttl_hours = _session_ttl_hours(db, user.role)
    session.last_seen_at = now
    session.expires_at = now + timedelta(hours=ttl_hours)
    db.commit()


def revoke_session(db: Session, session: UserSession) -> None:
    session.revoked_at = utc_now()
    db.commit()
