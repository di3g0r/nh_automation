"""Operation-number sequences (data model §2, phase 1b; used by phase 2, BR-19).

One row per order type; Trabajo and Retrabajo numbers are independent and
shared by every razón social.
"""

from __future__ import annotations

from sqlalchemy import CheckConstraint, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin

ORDER_TYPES = ("trabajo", "retrabajo")


class OrderSequence(Base, TimestampMixin):
    __tablename__ = "order_sequences"
    __table_args__ = (
        CheckConstraint("next_number >= 1", name="ck_order_sequences_next_number"),
        CheckConstraint(
            "order_type IN ('trabajo', 'retrabajo')", name="ck_order_sequences_order_type"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_type: Mapped[str] = mapped_column(String(16), unique=True, nullable=False)
    prefix: Mapped[str] = mapped_column(String(4), nullable=False)
    next_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
