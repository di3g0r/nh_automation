"""Key/value settings table (data model §2).

Defaults live in code; see app/services/settings_service.py.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin
from app.db.types import JSONVariant


class Setting(Base, TimestampMixin):
    __tablename__ = "settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    # Scalar or object: e.g. an hour count, a bool flag, or a nullable site id.
    value: Mapped[Any] = mapped_column(JSONVariant, nullable=False)
