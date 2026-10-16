"""Background runner for the PLC event processor (phase 4).

Runs as a daemon thread inside the `api` process (see DECISIONS 2026-10-15).
It waits on `LISTEN plc_events` (the insert trigger notifies on commit) and
also polls every `POLL_SECONDS` as a fallback, then calls
`plc_event_service.process_pending`.

A PostgreSQL session advisory lock makes sure only one processor runs even if
several API processes are started; the others wait and take over if it dies.
Connection errors are logged and retried. PostgreSQL only.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable

import psycopg
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.services import plc_event_service

logger = logging.getLogger(__name__)

POLL_SECONDS = 5.0
RETRY_SECONDS = 5.0
ADVISORY_LOCK_KEY = 4_174_001  # arbitrary, constant: "the PLC event processor"
CHANNEL = "plc_events"


def _psycopg_dsn(database_url: str) -> str:
    return make_url(database_url).set(drivername="postgresql").render_as_string(
        hide_password=False
    )


class PlcListener:
    def __init__(
        self, database_url: str, session_factory: Callable[[], Session] | None = None
    ) -> None:
        self._dsn = _psycopg_dsn(database_url)
        self._session_factory = session_factory
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="plc-events", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=POLL_SECONDS + 2)

    def _process(self) -> None:
        if self._session_factory is None:
            from app.db.session import SessionLocal

            self._session_factory = SessionLocal
        try:
            count = plc_event_service.process_pending(self._session_factory)
            if count:
                logger.info("Processed %s PLC event(s)", count)
        except Exception:  # noqa: BLE001 - keep the loop alive
            logger.exception("PLC event processing failed")

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                with psycopg.connect(self._dsn, autocommit=True) as conn:
                    if not self._wait_for_lock(conn):
                        return
                    conn.execute(f"LISTEN {CHANNEL}")
                    logger.info("PLC event processor started")
                    while not self._stop.is_set():
                        self._process()
                        # Returns on the first notification or after the timeout.
                        for _ in conn.notifies(timeout=POLL_SECONDS, stop_after=1):
                            pass
            except Exception:  # noqa: BLE001 - reconnect after a pause
                logger.exception("PLC event listener connection failed; retrying")
                self._stop.wait(RETRY_SECONDS)

    def _wait_for_lock(self, conn: psycopg.Connection) -> bool:
        while not self._stop.is_set():
            row = conn.execute("SELECT pg_try_advisory_lock(%s)", (ADVISORY_LOCK_KEY,)).fetchone()
            if row and row[0]:
                return True
            self._stop.wait(POLL_SECONDS)
        return False


def build_listener() -> PlcListener | None:
    """The listener for this process, or None when disabled or not on PostgreSQL."""
    settings = get_settings()
    if not settings.plc_event_processor:
        return None
    if not make_url(settings.database_url).get_backend_name().startswith("postgresql"):
        return None
    return PlcListener(settings.database_url)
