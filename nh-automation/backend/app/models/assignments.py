"""Machine assignments (data model §2, phase 3).

An order is split across one or more machines; each assignment has planned
liters and, once completed, actual liters. There is no operator column:
operators do not use the platform (v3.1). `assignment_events` records every
action with its source (`manual` from the platform, `plc` from phase 4).
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin
from app.models.catalogs import Machine

ASSIGNMENT_STATUSES = ("pending", "running", "paused", "completed", "cancelled")
ASSIGNMENT_EVENTS = (
    "assign", "start", "pause", "resume", "progress", "complete", "cancel", "error"
)
SOURCES = ("plc", "manual")


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN (" + ", ".join(f"'{v}'" for v in values) + ")"


class Assignment(Base, TimestampMixin):
    __tablename__ = "assignments"
    __table_args__ = (
        # BR-7: one assignment per machine per order.
        UniqueConstraint("order_id", "machine_id", name="uq_assignments_order_machine"),
        CheckConstraint(_in("status", ASSIGNMENT_STATUSES), name="ck_assignments_status"),
        CheckConstraint(
            "last_source IS NULL OR " + _in("last_source", SOURCES),
            name="ck_assignments_last_source",
        ),
        CheckConstraint("planned_liters > 0", name="ck_assignments_planned_liters"),
        CheckConstraint(
            "actual_liters IS NULL OR actual_liters >= 0", name="ck_assignments_actual_liters"
        ),
        Index("ix_assignments_machine_status", "machine_id", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(
        ForeignKey("work_orders.id", ondelete="CASCADE"), nullable=False, index=True
    )
    machine_id: Mapped[int] = mapped_column(ForeignKey("machines.id"), nullable=False)
    planned_liters: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    actual_liters: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    queue_position: Mapped[int] = mapped_column(Integer, nullable=False)
    last_source: Mapped[str | None] = mapped_column(String(8), nullable=True)
    assigned_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    assigned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    machine: Mapped[Machine] = relationship(lazy="joined")


class AssignmentEvent(Base, TimestampMixin):
    """Append-only log of assignment actions. `user_id` for manual actions,
    `machine_id` for PLC actions (phase 4)."""

    __tablename__ = "assignment_events"
    __table_args__ = (
        CheckConstraint(_in("event", ASSIGNMENT_EVENTS), name="ck_assignment_events_event"),
        CheckConstraint(_in("source", SOURCES), name="ck_assignment_events_source"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    assignment_id: Mapped[int] = mapped_column(
        ForeignKey("assignments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    event: Mapped[str] = mapped_column(String(16), nullable=False)
    liters: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    source: Mapped[str] = mapped_column(String(8), nullable=False)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    machine_id: Mapped[int | None] = mapped_column(ForeignKey("machines.id"), nullable=True)
    # `error` events (phase 4): the PLC's code and message.
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
