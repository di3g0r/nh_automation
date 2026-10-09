"""User CRUD and the last-master-admin protection (BR-15, FR-USR)."""

from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.errors import AppError, not_found
from app.core.permissions import Role
from app.core.security import hash_secret
from app.models.user import User
from app.schemas.user import ResetCredentials, UserCreate, UserUpdate
from app.services import audit_service


def _user_snapshot(user: User) -> dict:
    return {
        "username": user.username,
        "full_name": user.full_name,
        "role": user.role,
        "is_active": user.is_active,
    }


def count_active_master_admins(db: Session, exclude_user_id: int | None = None) -> int:
    query = db.query(func.count(User.id)).filter(
        User.role == Role.MASTER_ADMIN.value, User.is_active.is_(True)
    )
    if exclude_user_id is not None:
        query = query.filter(User.id != exclude_user_id)
    return query.scalar() or 0


def get_by_id(db: Session, user_id: int) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise not_found("Usuario")
    return user


def get_by_username(db: Session, username: str) -> User | None:
    return db.query(User).filter(User.username == username).first()


def list_users(
    db: Session, *, search: str | None = None, page: int = 1, page_size: int = 50
) -> tuple[list[User], int]:
    query = db.query(User)
    if search:
        like = f"%{search}%"
        query = query.filter((User.username.ilike(like)) | (User.full_name.ilike(like)))
    total = query.count()
    items = (
        query.order_by(User.username).offset((page - 1) * page_size).limit(page_size).all()
    )
    return items, total


def create_user(db: Session, data: UserCreate, *, actor: User) -> User:
    if get_by_username(db, data.username) is not None:
        raise AppError(
            "USERNAME_TAKEN", "Ya existe un usuario con ese nombre de usuario.", 409
        )

    user = User(
        username=data.username,
        full_name=data.full_name,
        role=data.role,
        password_hash=hash_secret(data.password),
        pin_hash=hash_secret(data.pin) if data.pin else None,
        is_active=True,
    )
    db.add(user)
    db.flush()
    audit_service.record(
        db, user=actor, entity="user", entity_id=user.id, action="create",
        before=None, after=_user_snapshot(user),
    )
    db.commit()
    db.refresh(user)
    return user


def update_user(db: Session, user_id: int, data: UserUpdate, *, actor: User) -> User:
    user = get_by_id(db, user_id)
    before = _user_snapshot(user)

    if data.role is not None and data.role != user.role:
        if user.role == Role.MASTER_ADMIN.value and data.role != Role.MASTER_ADMIN.value:
            if count_active_master_admins(db, exclude_user_id=user.id) == 0:
                raise AppError(
                    "LAST_MASTER_ADMIN",
                    "No se puede quitar el rol de administrador maestro: "
                    "debe existir al menos uno activo.",
                    409,
                )
        user.role = data.role

    if data.full_name is not None:
        user.full_name = data.full_name

    db.flush()
    audit_service.record(
        db, user=actor, entity="user", entity_id=user.id, action="update",
        before=before, after=_user_snapshot(user),
    )
    db.commit()
    db.refresh(user)
    return user


def set_active(db: Session, user_id: int, *, active: bool, actor: User) -> User:
    user = get_by_id(db, user_id)
    before = _user_snapshot(user)

    if not active and user.role == Role.MASTER_ADMIN.value:
        if count_active_master_admins(db, exclude_user_id=user.id) == 0:
            raise AppError(
                "LAST_MASTER_ADMIN",
                "No se puede desactivar al último administrador maestro activo.",
                409,
            )

    user.is_active = active
    if not active:
        user.locked_until = None
    db.flush()
    audit_service.record(
        db, user=actor, entity="user", entity_id=user.id,
        action="deactivate" if not active else "activate",
        before=before, after=_user_snapshot(user),
    )
    db.commit()
    db.refresh(user)
    return user


def reset_credentials(db: Session, user_id: int, data: ResetCredentials, *, actor: User) -> User:
    user = get_by_id(db, user_id)
    if data.password is None and data.pin is None:
        raise AppError(
            "NO_CREDENTIALS_PROVIDED", "Debe proporcionar una nueva contraseña o PIN.", 422
        )

    if data.password is not None:
        user.password_hash = hash_secret(data.password)
    if data.pin is not None:
        user.pin_hash = hash_secret(data.pin)

    user.failed_attempts = 0
    user.locked_until = None
    db.flush()
    audit_service.record(
        db, user=actor, entity="user", entity_id=user.id, action="reset_credentials",
        before={"username": user.username}, after={"username": user.username},
    )
    db.commit()
    db.refresh(user)
    return user


def change_own_credentials(
    db: Session, user: User, *, new_password: str | None, new_pin: str | None
) -> User:
    if new_password is not None:
        user.password_hash = hash_secret(new_password)
    if new_pin is not None:
        user.pin_hash = hash_secret(new_pin)
    db.flush()
    audit_service.record(
        db, user=user, entity="user", entity_id=user.id, action="change_credentials",
        before={"username": user.username}, after={"username": user.username},
    )
    db.commit()
    db.refresh(user)
    return user
