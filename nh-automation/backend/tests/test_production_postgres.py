"""Phase 3 production actions on real PostgreSQL (SQLite ignores FOR UPDATE).

Regression: the machine row lock (BR-14) used to fail on PostgreSQL with
"FOR UPDATE cannot be applied to the nullable side of an outer join"
because `Machine.site` is eager-loaded with an outer join.

Skipped unless TEST_POSTGRES_URL points to an empty scratch database (see
test_orders_concurrency.py).
"""

from __future__ import annotations

import os
import threading
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.errors import AppError
from app.db.base import Base
from app.models.assignments import Assignment
from app.models.catalogs import Client, Machine, Product, RazonSocial
from app.models.orders import WorkOrder
from app.models.user import User
from app.schemas.orders import BaseProductIn, OrderCreate
from app.schemas.production import AssignmentIn
from app.services import assignment_service, order_service, seed_service, stock_service
from app.services.assignment_service import Actor
from app.services.stock_service import ItemRef

pytestmark = pytest.mark.skipif(
    not os.environ.get("TEST_POSTGRES_URL"),
    reason="set TEST_POSTGRES_URL to an empty scratch Postgres DB to run",
)


@pytest.fixture()
def factory():
    engine = create_engine(os.environ["TEST_POSTGRES_URL"], pool_size=20)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    try:
        yield sessionmaker(bind=engine, autoflush=False)
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()


def _seed(factory) -> dict[str, int]:
    with factory() as db:
        site = seed_service.ensure_base_catalogs(db)
        rs = db.query(RazonSocial).filter(RazonSocial.code == "ANB").one()
        user = User(username="jefe", full_name="Jefe", role="production_manager",
                    password_hash="x")
        cliente = Client(name="C", code="C", is_active=True)
        base = Product(code="BASE", name="BASE", provider="P", presentation="1000",
                       razon_social_id=rs.id, is_active=True)
        finished = Product(code="FIN", name="FIN", provider="P", presentation="1X20",
                           razon_social_id=rs.id, is_active=True)
        m1 = Machine(code="M01", name="M01", site_id=site.id)
        m4 = Machine(code="M04", name="M04", site_id=site.id)
        db.add_all([user, cliente, base, finished, m1, m4])
        db.flush()
        stock_service.apply_movement(
            db, site_id=site.id, item=ItemRef("product", base.id), movement_type="receipt",
            quantity=Decimal("1000"), user=None,
        )
        db.commit()
        return {"site": site.id, "user": user.id, "client": cliente.id, "base": base.id,
                "finished": finished.id, "M01": m1.id, "M04": m4.id}


def _assigned_order(factory, ids, split: list[tuple[str, str]]) -> int:
    with factory() as db:
        user = db.get(User, ids["user"])
        order = order_service.create_order(db, OrderCreate(
            order_type="trabajo", client_id=ids["client"],
            base_products=[BaseProductIn(product_id=ids["base"], liters=Decimal("100"))],
            finished_product_id=ids["finished"],
        ), actor=user)
        order_service.set_expiry(db, order.id, date(2029, 3, 1), actor=user)
        assignment_service.set_assignments(db, order.id, [
            AssignmentIn(machine_id=ids[m], planned_liters=Decimal(q)) for m, q in split
        ], actor=user)
        return order.id


def _assignment_id(db, order_id: int, machine_id: int) -> int:
    return db.query(Assignment.id).filter(
        Assignment.order_id == order_id, Assignment.machine_id == machine_id
    ).one()[0]


def test_full_production_cycle_on_postgres(factory):
    ids = _seed(factory)
    order_id = _assigned_order(factory, ids, [("M01", "70"), ("M04", "30")])
    with factory() as db:
        actor = Actor.manual(db.get(User, ids["user"]))
        a1 = _assignment_id(db, order_id, ids["M01"])
        a4 = _assignment_id(db, order_id, ids["M04"])
        assignment_service.start(db, a1, actor)
        assignment_service.pause(db, a1, actor)
        assert db.get(WorkOrder, order_id).status == "paused"
        assignment_service.resume(db, a1, actor)
        assignment_service.start(db, a4, actor)
        assert db.get(WorkOrder, order_id).status == "in_progress"
        assignment_service.complete(db, a1, Decimal("70"), actor)
        assignment_service.complete(db, a4, Decimal("29"), actor)
        assert db.get(WorkOrder, order_id).status == "completed"
        assert stock_service.get_on_hand(
            db, ids["site"], ItemRef("product", ids["base"])
        ) == Decimal("901")


def test_queue_reorder_on_postgres(factory):
    ids = _seed(factory)
    first = _assigned_order(factory, ids, [("M01", "100")])
    second = _assigned_order(factory, ids, [("M01", "100")])
    with factory() as db:
        user = db.get(User, ids["user"])
        moved = assignment_service.reorder(
            db, _assignment_id(db, second, ids["M01"]), 1, actor=user
        )
        assert moved.queue_position == 1
        assert db.get(Assignment, _assignment_id(db, first, ids["M01"])).queue_position == 2


def test_concurrent_starts_on_one_machine_only_one_runs(factory):
    """BR-14: the machine row lock serializes starts; the queue's next
    assignment wins and the other is refused."""
    ids = _seed(factory)
    order_ids = [_assigned_order(factory, ids, [("M01", "100")]) for _ in range(2)]
    with factory() as db:
        assignment_ids = [_assignment_id(db, o, ids["M01"]) for o in order_ids]
    ok: list[int] = []
    errors: list[str] = []
    barrier = threading.Barrier(len(assignment_ids))

    def worker(assignment_id: int) -> None:
        with factory() as db:
            actor = Actor.manual(db.get(User, ids["user"]))
            barrier.wait()
            try:
                assignment_service.start(db, assignment_id, actor)
                ok.append(assignment_id)
            except AppError as exc:
                db.rollback()
                errors.append(exc.code)

    threads = [threading.Thread(target=worker, args=(a,)) for a in assignment_ids]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)
        assert not t.is_alive(), "worker hung (deadlock?)"
    assert ok == [assignment_ids[0]]
    assert errors == ["MACHINE_NOT_READY"]
