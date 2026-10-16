"""PLC database interface (data model §2.2, phase 4).

`plc_events` is the inbox the PLCs insert into while logged in with their own
PostgreSQL role. A `BEFORE INSERT` trigger (created by the phase-4 migration,
PostgreSQL only) sets `machine_id` from the logged-in role, stamps
`received_at`, clears the processing columns and updates
`machines.last_seen_at`. The backend event processor
(`plc_event_service`) fills `processed_at`, `result` and `reject_reason`.

The read-only views the PLCs query (`plc_pending_assignments`,
`plc_assignment_base_products`, `plc_assignment_packaging`) exist only in the
migration: they are not mapped here.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin

PLC_EVENTS = ("start", "progress", "pause", "resume", "complete", "error")
PLC_RESULTS = ("applied", "duplicate", "rejected")
# Reason codes stored at the start of `reject_reason` ("CODE: detail").
REJECT_REASONS = ("NOT_ON_MACHINE", "INVALID_TRANSITION", "NOT_FIRST_IN_QUEUE", "BAD_PAYLOAD")


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN (" + ", ".join(f"'{v}'" for v in values) + ")"


class PlcEvent(Base, TimestampMixin):
    __tablename__ = "plc_events"
    __table_args__ = (
        CheckConstraint(_in("event", PLC_EVENTS), name="ck_plc_events_event"),
        CheckConstraint(
            "result IS NULL OR " + _in("result", PLC_RESULTS), name="ck_plc_events_result"
        ),
        CheckConstraint("liters IS NULL OR liters >= 0", name="ck_plc_events_liters"),
        # The processor's work list (BR-13: received_at order).
        Index(
            "ix_plc_events_unprocessed", "received_at", "id",
            postgresql_where=text("processed_at IS NULL"),
        ),
        Index("ix_plc_events_machine_seq", "machine_id", "seq"),
        Index("ix_plc_events_machine_event", "machine_id", "event", "id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # Set by the trigger from the logged-in PLC role; the PLC cannot choose it.
    machine_id: Mapped[int] = mapped_column(ForeignKey("machines.id"), nullable=False)
    # No FK: an unknown id is stored and rejected by the processor (NOT_ON_MACHINE).
    assignment_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    event: Mapped[str] = mapped_column(String(16), nullable=False)
    # Cumulative liters for the assignment (not a delta).
    liters: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    # Optional, increasing per machine. A repeated (machine, seq) is a duplicate.
    seq: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    # PLC clock (informative). Without an offset it is read as local time
    # (the PLC roles have timezone America/Mazatlan, NFR-7a).
    plc_timestamp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Authoritative time (trigger: now()).
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    result: Mapped[str | None] = mapped_column(String(16), nullable=True)
    reject_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
