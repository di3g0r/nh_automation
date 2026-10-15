"""User table (data model §2). Roles: master_admin, admin, production_manager
(operator is legacy: allowed by ck_users_role for old rows, cannot log in)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.permissions import Role
from app.db.base import Base, TimestampMixin

ROLE_CHECK = "role IN (" + ", ".join(f"'{r.value}'" for r in Role) + ")"


class User(Base, TimestampMixin):
    __tablename__ = "users"
    __table_args__ = (CheckConstraint(ROLE_CHECK, name="ck_users_role"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    # One of app.core.permissions.Role; validated by the schemas and by the
    # ck_users_role CHECK constraint (a new role needs a migration).
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    pin_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    failed_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<User {self.username} ({self.role})>"
