"""Phase 4 on real PostgreSQL: PLC logins, views, insert trigger, event
processor and the LISTEN loop, run against the real migrations.

Each test logs in as test PLC roles (no simulator) created by
`plc_credentials_service`. Machine codes start with `T4` so the cluster-wide
roles (`plc_t4m01`, ...) never clash with the dev database's `plc_m01`; they
are dropped at the end.

Skipped unless TEST_POSTGRES_URL points to an EMPTY scratch database (its
public schema is dropped and rebuilt with `alembic upgrade head`), e.g.
TEST_POSTGRES_URL=postgresql+psycopg://nh_app:change-me@localhost:5432/nh_phase4
The URL's user must be able to create roles.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.exc import DBAPIError, ProgrammingError
from sqlalchemy.orm import sessionmaker

from app.models.assignments import Assignment
from app.models.catalogs import Client, Machine, PackagingItem, Product, RazonSocial
from app.models.orders import WorkOrder
from app.models.plc import PlcEvent
from app.models.stock import StockMovement
from app.models.user import User
from app.schemas.orders import BaseProductIn, OrderCreate, PackagingIn
from app.schemas.production import AssignmentIn
from app.services import (
    assignment_service,
    order_service,
    plc_credentials_service,
    plc_event_service,
    production_service,
    seed_service,
    settings_service,
    stock_service,
)
from app.services.assignment_service import Actor
from app.services.plc_listener import PlcListener
from app.services.stock_service import ItemRef

URL = os.environ.get("TEST_POSTGRES_URL", "")
pytestmark = pytest.mark.skipif(
    not URL, reason="set TEST_POSTGRES_URL to an empty scratch Postgres DB to run"
)
BACKEND = Path(__file__).resolve().parent.parent
CODES = ("T4M01", "T4M02")


@pytest.fixture(scope="module")
def engine():
    eng = create_engine(URL)
    with eng.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
    env = {**os.environ, "DATABASE_URL": URL, "PLC_EVENT_PROCESSOR": "false"}
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"], cwd=BACKEND, env=env, check=True,
        capture_output=True,
    )
    yield eng
    with eng.begin() as conn:
        # Leave the scratch database empty for the other Postgres-only tests.
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
        for code in CODES:
            name = plc_credentials_service.username_for(code)
            conn.execute(text(f'DROP ROLE IF EXISTS "{name}"'))
    eng.dispose()


@pytest.fixture()
def factory(engine):
    with engine.begin() as conn:
        tables = conn.execute(
            text(
                "SELECT string_agg(quote_ident(tablename), ', ') FROM pg_tables "
                "WHERE schemaname = 'public' AND tablename <> 'alembic_version'"
            )
        ).scalar_one()
        conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
    return sessionmaker(bind=engine, autoflush=False)


class World:
    def __init__(self, factory, ids, passwords):
        self.factory = factory
        self.ids = ids
        self.passwords = passwords
        self._engines: dict[str, Engine] = {}

    def plc(self, code: str) -> Engine:
        """An engine logged in as the machine's PLC role."""
        if code not in self._engines:
            url = make_url(URL).set(
                username=plc_credentials_service.username_for(code),
                password=self.passwords[code],
            )
            self._engines[code] = create_engine(url, poolclass=None)
        return self._engines[code]

    def close(self) -> None:
        for eng in self._engines.values():
            eng.dispose()


@pytest.fixture()
def world(factory):
    with factory() as db:
        settings_service.ensure_defaults(db)
        site = seed_service.ensure_base_catalogs(db)
        rs = db.query(RazonSocial).filter(RazonSocial.code == "ANB").one()
        admin = User(username="director", full_name="Director", role="master_admin",
                     password_hash="x")
        jefe = User(username="jefe", full_name="Jefe", role="production_manager",
                    password_hash="x")
        cliente = Client(name="Agrícola", code="AGV", is_active=True)
        base = Product(code="QVR200C1XL09M01", name="BASE CALCIO", provider="QVR",
                       presentation="1000", razon_social_id=rs.id, is_active=True)
        finished = Product(code="QVR200C1XL20F003", name="NH-CALCIO", provider="QVR",
                           presentation="1X20", razon_social_id=rs.id, is_active=True)
        machines = [Machine(code=c, name=f"Máquina {c}", site_id=site.id) for c in CODES]
        db.add_all([admin, jefe, cliente, base, finished, *machines])
        db.flush()
        envase = db.query(PackagingItem).filter(PackagingItem.code == "ENVLI20001").one()
        for item, qty in ((ItemRef("product", base.id), "5000"),
                          (ItemRef("packaging", envase.id), "500")):
            stock_service.apply_movement(db, site_id=site.id, item=item,
                                         movement_type="receipt", quantity=Decimal(qty),
                                         user=None)
        db.commit()
        ids = {"site": site.id, "admin": admin.id, "jefe": jefe.id, "client": cliente.id,
               "base": base.id, "finished": finished.id, "envase": envase.id,
               **{m.code: m.id for m in machines}}
    passwords = {}
    for code in CODES:
        with factory() as db:
            creds = plc_credentials_service.create_or_rotate(
                db, ids[code], actor=db.get(User, ids["admin"])
            )
            passwords[code] = creds.password
    w = World(factory, ids, passwords)
    yield w
    w.close()


def _order(w: World, liters: str, split: list[tuple[str, str]] | None, *,
           expiry: bool = True, comments: tuple[str, ...] = ()) -> int:
    with w.factory() as db:
        jefe = db.get(User, w.ids["jefe"])
        order = order_service.create_order(db, OrderCreate(
            order_type="trabajo", client_id=w.ids["client"],
            base_products=[BaseProductIn(product_id=w.ids["base"], liters=Decimal(liters))],
            finished_product_id=w.ids["finished"],
            packaging=[PackagingIn(packaging_item_id=w.ids["envase"], planned_qty=50)],
            labels_planned=50,
            comment=comments[0] if comments else None,
        ), actor=jefe)
        for c in comments[1:]:
            order_service.add_comment(db, order.id, c, actor=jefe)
        if expiry:
            order_service.set_expiry(db, order.id, date(2029, 3, 1), actor=jefe)
        if split:
            assignment_service.set_assignments(db, order.id, [
                AssignmentIn(machine_id=w.ids[code], planned_liters=Decimal(liters))
                for code, liters in split
            ], actor=jefe)
        return order.id


def _assignment(w: World, order_id: int, code: str) -> int:
    with w.factory() as db:
        return db.query(Assignment.id).filter(
            Assignment.order_id == order_id, Assignment.machine_id == w.ids[code]
        ).scalar()


def _rows(w: World, code: str, sql: str, **params) -> list[dict]:
    with w.plc(code).connect() as conn:
        return [dict(r._mapping) for r in conn.execute(text(sql), params)]


def _send(w: World, code: str, assignment_id: int | None, event: str,
          liters: str | None = None, seq: int | None = None, **extra) -> None:
    cols = {"assignment_id": assignment_id, "event": event,
            "liters": Decimal(liters) if liters is not None else None, "seq": seq, **extra}
    names = ", ".join(cols)
    values = ", ".join(f":{k}" for k in cols)
    with w.plc(code).begin() as conn:
        conn.execute(text(f"INSERT INTO plc_events ({names}) VALUES ({values})"), cols)


def _process(w: World) -> int:
    return plc_event_service.process_pending(w.factory)


def _status(w: World, order_id: int) -> str:
    with w.factory() as db:
        return db.get(WorkOrder, order_id).status


# Roles and views ------------------------------------------------------------------------


def test_logins_created_with_limits(world):
    with world.factory() as db:
        rows = db.execute(text(
            "SELECT r.rolname, r.rolconnlimit, r.rolconfig, r.rolsuper, "
            "pg_has_role(r.rolname, 'plc_machine', 'MEMBER') AS member "
            "FROM pg_roles r WHERE r.rolname IN ('plc_t4m01', 'plc_t4m02') ORDER BY 1"
        )).all()
        machines = {m.code: m.plc_db_username for m in db.query(Machine)}
    assert [r.rolname for r in rows] == ["plc_t4m01", "plc_t4m02"]
    for r in rows:
        assert r.rolconnlimit == 3 and r.member and not r.rolsuper
        assert "statement_timeout=5s" in r.rolconfig
        assert "TimeZone=America/Mazatlan" in r.rolconfig
    assert machines == {"T4M01": "plc_t4m01", "T4M02": "plc_t4m02"}


def test_rotation_invalidates_old_password(world):
    old = world.passwords["T4M01"]
    with world.factory() as db:
        creds = plc_credentials_service.create_or_rotate(
            db, world.ids["T4M01"], actor=db.get(User, world.ids["admin"])
        )
    assert creds.created is False and creds.password != old
    world.close()
    world._engines.clear()
    with pytest.raises(DBAPIError):
        _rows(world, "T4M01", "SELECT 1")
    world.close()
    world._engines.clear()
    world.passwords["T4M01"] = creds.password
    assert _rows(world, "T4M01", "SELECT 1 AS one") == [{"one": 1}]


def test_scenario1_each_plc_sees_only_its_assignment(world):
    order_id = _order(world, "1000", [("T4M01", "500"), ("T4M02", "500")],
                      comments=("Cambio de etiqueta", "Reen #301"))
    a1, a2 = _assignment(world, order_id, "T4M01"), _assignment(world, order_id, "T4M02")
    rows1 = _rows(world, "T4M01", "SELECT * FROM plc_pending_assignments")
    rows2 = _rows(world, "T4M02", "SELECT * FROM plc_pending_assignments")
    assert [r["assignment_id"] for r in rows1] == [a1]
    assert [r["assignment_id"] for r in rows2] == [a2]
    r = rows1[0]
    assert r["operation_number"] == "T-1 ANB" and r["order_type"] == "trabajo"
    assert (r["queue_position"], r["status"]) == (1, "pending")
    assert (r["finished_code"], r["finished_presentation"]) == ("QVR200C1XL20F003", "1X20")
    assert r["planned_liters"] == Decimal("500.00") and r["actual_liters"] is None
    assert r["expiry_date"] == date(2029, 3, 1)
    assert r["comments"] == "Reen #301 | Cambio de etiqueta"  # newest first
    assert (r["labels_planned"], r["barcode_mode"]) == (50, "per_container")
    base = _rows(world, "T4M01", "SELECT * FROM plc_assignment_base_products")
    assert base == [{"assignment_id": a1, "position": 1, "base_code": "QVR200C1XL09M01",
                     "base_name": "BASE CALCIO", "liters": Decimal("500.00")}]
    pack = _rows(world, "T4M02", "SELECT * FROM plc_assignment_packaging")
    assert pack == [{"assignment_id": a2, "packaging_code": "ENVLI20001",
                     "packaging_description": "Envase 20 L Fisher", "planned_qty": 50,
                     "labels_planned": 50, "barcode_mode": "per_container"}]


def test_queue_position_current_first(world):
    first = _order(world, "100", [("T4M01", "100")])
    second = _order(world, "100", [("T4M01", "100")])
    a_first, a_second = _assignment(world, first, "T4M01"), _assignment(world, second, "T4M01")
    with world.factory() as db:  # second goes first in the queue
        assignment_service.reorder(db, a_second, 1, actor=db.get(User, world.ids["jefe"]))
    _send(world, "T4M01", a_second, "start")
    _process(world)
    rows = _rows(world, "T4M01", "SELECT assignment_id, queue_position, status "
                                 "FROM plc_pending_assignments")
    assert rows == [
        {"assignment_id": a_second, "queue_position": 1, "status": "running"},
        {"assignment_id": a_first, "queue_position": 2, "status": "pending"},
    ]


def test_scenario5_order_without_expiry_not_visible(world):
    order_id = _order(world, "100", [("T4M01", "100")], expiry=False)
    assert _status(world, order_id) == "created"
    assert _rows(world, "T4M01", "SELECT * FROM plc_pending_assignments") == []
    assert _rows(world, "T4M01", "SELECT * FROM plc_assignment_base_products") == []


@pytest.mark.parametrize("sql", [
    "SELECT * FROM work_orders",
    "SELECT * FROM assignments",
    "SELECT * FROM machines",
    "SELECT * FROM users",
    "SELECT * FROM plc_events",
    "UPDATE assignments SET status = 'completed'",
    "DELETE FROM stock_levels",
    "UPDATE plc_events SET result = 'applied'",
    "DELETE FROM plc_events",
    "INSERT INTO plc_events (machine_id, assignment_id, event) VALUES (2, 1, 'start')",
    "INSERT INTO plc_events (assignment_id, event, result) VALUES (1, 'start', 'applied')",
    "CREATE TABLE intrusa (id int)",
])
def test_scenario3_plc_cannot_touch_business_tables(world, sql):
    with pytest.raises(ProgrammingError) as exc:
        with world.plc("T4M01").begin() as conn:
            conn.execute(text(sql))
    assert "permission denied" in str(exc.value).lower()


# Trigger ---------------------------------------------------------------------------------


def test_trigger_sets_machine_and_contact(world):
    order_id = _order(world, "1000", [("T4M01", "500"), ("T4M02", "500")])
    a2 = _assignment(world, order_id, "T4M02")
    # The PLC of T4M01 sends an event for T4M02's assignment: stored as T4M01's.
    _send(world, "T4M01", a2, "start", seq=1, plc_timestamp="2026-10-15 08:00:00")
    with world.factory() as db:
        ev = db.query(PlcEvent).one()
        m1 = db.get(Machine, world.ids["T4M01"])
        assert ev.machine_id == m1.id and ev.processed_at is None and ev.result is None
        assert m1.last_seen_at is not None and m1.last_seen_at == ev.received_at
        # No offset = local time (UTC-7).
        assert ev.plc_timestamp == datetime(2026, 10, 15, 15, 0, tzinfo=UTC)
    _process(world)
    with world.factory() as db:
        ev = db.query(PlcEvent).one()
        assert ev.result == "rejected" and ev.reject_reason.startswith("NOT_ON_MACHINE")
        assert db.get(Assignment, a2).status == "pending"


@pytest.mark.parametrize("event,liters,message", [
    ("arrancar", None, "evento no valido"),
    ("progress", "-1", "negativos"),
])
def test_trigger_rejects_bad_inserts(world, event, liters, message):
    with pytest.raises(DBAPIError) as exc:
        _send(world, "T4M01", 1, event, liters)
    assert message in str(exc.value).lower()


def test_inactive_machine_cannot_insert(world):
    with world.factory() as db:
        db.get(Machine, world.ids["T4M01"]).is_active = False
        db.commit()
    with pytest.raises(DBAPIError) as exc:
        _send(world, "T4M01", 1, "start")
    assert "maquina activa" in str(exc.value).lower()


# Scenarios --------------------------------------------------------------------------------


def test_scenario1_and_2_split_completed_by_plcs(world):
    order_id = _order(world, "1000", [("T4M01", "500"), ("T4M02", "500")])
    a1, a2 = _assignment(world, order_id, "T4M01"), _assignment(world, order_id, "T4M02")
    for code, a, final in (("T4M01", a1, "500"), ("T4M02", a2, "495")):
        _send(world, code, a, "start", seq=1)
        _send(world, code, a, "progress", "100", seq=2)
        _send(world, code, a, "progress", "300", seq=3)
        _send(world, code, a, "progress", "300", seq=3)  # scenario 2: duplicate
        _send(world, code, a, "complete", final, seq=4)
        _send(world, code, a, "complete", final, seq=4)  # scenario 2: duplicate
    _process(world)
    with world.factory() as db:
        results = sorted(r for (r,) in db.query(PlcEvent.result))
        assert results.count("duplicate") == 4 and results.count("applied") == 8
        order = db.get(WorkOrder, order_id)
        assert order.status == "completed"
        diff = production_service.difference(
            db, order, assignment_service.order_assignments(db, order.id)
        )
        assert diff.difference == Decimal("-5.00")  # Faltante 5.00 L
        assert order_id in {o.id for o in production_service.to_close(db)}
        produced = sum(
            Decimal(m.quantity) for m in db.query(StockMovement).filter(
                StockMovement.order_id == order_id, StockMovement.type == "production")
        )
        consumed = sum(
            Decimal(m.quantity) for m in db.query(StockMovement).filter(
                StockMovement.order_id == order_id, StockMovement.type == "consumption",
                StockMovement.product_id == world.ids["base"])
        )
        assert produced == Decimal("995.00") and consumed == Decimal("-995.00")
        on_hand = stock_service.get_on_hand(db, world.ids["site"],
                                            ItemRef("packaging", world.ids["envase"]))
        assert on_hand == Decimal("450")  # planned packaging consumed on completion


def test_scenario4_pause_resume_manual_completion(world):
    order_id = _order(world, "100", [("T4M01", "100")])
    a1 = _assignment(world, order_id, "T4M01")
    _send(world, "T4M01", a1, "start", seq=1)
    _send(world, "T4M01", a1, "progress", "40", seq=2)
    _send(world, "T4M01", a1, "pause", seq=3)  # end of shift
    _process(world)
    assert _status(world, order_id) == "paused"
    _send(world, "T4M01", a1, "resume", seq=4)
    _process(world)
    assert _status(world, order_id) == "in_progress"
    with world.factory() as db:  # PLC failure: completed from the platform
        assignment_service.complete(db, a1, Decimal("99"),
                                    Actor.manual(db.get(User, world.ids["jefe"])))
    assert _status(world, order_id) == "completed"
    with world.factory() as db:
        history = order_service.history(db, order_id)
    sources = {(h.action, (h.after or {}).get("source")) for h in history}
    assert {("start", "plc"), ("pause", "plc"), ("resume", "plc"),
            ("complete", "manual")} <= sources
    # The PLC no longer sees it.
    assert _rows(world, "T4M01", "SELECT * FROM plc_pending_assignments") == []


def test_listener_applies_events_within_seconds(world):
    """NOTIFY wakes the background processor (NFR-3: applied within 5 s)."""
    order_id = _order(world, "100", [("T4M01", "100")])
    a1 = _assignment(world, order_id, "T4M01")
    listener = PlcListener(URL, session_factory=world.factory)
    listener.start()
    try:
        time.sleep(1.0)  # let it LISTEN
        sent = time.monotonic()
        _send(world, "T4M01", a1, "start", seq=1)
        while time.monotonic() - sent < 10:
            if _status(world, order_id) == "in_progress":
                break
            time.sleep(0.1)
        elapsed = time.monotonic() - sent
    finally:
        listener.stop()
    assert _status(world, order_id) == "in_progress"
    assert elapsed < 5
