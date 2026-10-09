"""UTC <-> America/Mazatlan helpers (NFR-7a).

All timestamps are stored in UTC. Everything shown to a user (screens, prints,
exports, history, audit) is converted to local time with these helpers.
America/Mazatlan is UTC-7 year round (no DST), but we use the IANA zone name
rather than a hardcoded offset so the rule stays correct if that ever changes.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

LOCAL_TZ_NAME = "America/Mazatlan"
LOCAL_TZ = ZoneInfo(LOCAL_TZ_NAME)


def utc_now() -> datetime:
    """Current instant, timezone-aware, in UTC. Use this instead of datetime.utcnow()."""
    return datetime.now(UTC)


def ensure_aware(dt: datetime) -> datetime:
    """Treat a naive datetime as UTC.

    SQLite (used only in tests, see app/db/types.py) silently drops tzinfo on
    DateTime(timezone=True) columns; Postgres does not. Values read back from
    the database are always logically UTC, so this makes comparisons against
    utc_now() safe on both engines.
    """
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt


def to_local(dt: datetime) -> datetime:
    """Convert a timezone-aware (or naive-UTC) datetime to America/Mazatlan."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(LOCAL_TZ)


def to_utc(dt: datetime) -> datetime:
    """Convert a timezone-aware (or naive-local) datetime to UTC."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=LOCAL_TZ)
    return dt.astimezone(UTC)


def local_today(now: datetime | None = None) -> date:
    """The current local ("today") calendar day, per NFR-7a.

    A UTC timestamp at 06:30 UTC is 23:30 the previous local day
    (America/Mazatlan is UTC-7), so "today" must always be computed from the
    local conversion, never from the UTC date directly.
    """
    reference = now if now is not None else utc_now()
    return to_local(reference).date()
