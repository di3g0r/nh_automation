from datetime import UTC, date, datetime

from app.core.timezone import local_today, to_local, to_utc


def test_utc_0630_is_previous_local_day():
    # America/Mazatlan is UTC-7 year round (no DST): 06:30 UTC on day D
    # is 23:30 local on day D-1.
    dt = datetime(2026, 3, 15, 6, 30, tzinfo=UTC)
    assert local_today(dt) == date(2026, 3, 14)


def test_to_local_converts_offset():
    dt = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    local = to_local(dt)
    assert local.hour == 5
    assert local.utcoffset().total_seconds() == -7 * 3600


def test_to_utc_roundtrip():
    naive_local = datetime(2026, 6, 1, 8, 0)
    as_utc = to_utc(naive_local)
    assert as_utc.tzinfo is not None
    back = to_local(as_utc)
    assert back.hour == 8
    assert back.day == 1


def test_no_dst_in_july():
    # No DST means the offset is the same in winter and summer.
    winter = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    summer = datetime(2026, 7, 1, 12, 0, tzinfo=UTC)
    assert to_local(winter).utcoffset() == to_local(summer).utcoffset()
