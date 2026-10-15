"""BR-3 / BR-19 concurrency on real PostgreSQL (SQLite ignores FOR UPDATE).

Skipped unless TEST_POSTGRES_URL points to an empty scratch database, e.g.
TEST_POSTGRES_URL=postgresql+psycopg://nh_app:...@localhost:5432/nh_scratch
"""

from __future__ import annotations

import os
import threading
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.errors import AppError
from app.db.base import Base
from app.models.catalogs import Client, Product, RazonSocial
from app.models.orders import Reservation, WorkOrder
from app.models.user import User
from app.schemas.orders import BaseProductIn, OrderCreate, OrderUpdate
from app.services import order_service, seed_service, stock_service
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


def _seed(factory, stock: dict[str, str]) -> dict[str, int]:
    with factory() as db:
        site = seed_service.ensure_base_catalogs(db)
        rs = db.query(RazonSocial).filter(RazonSocial.code == "ANB").one()
        user = User(username="u", full_name="U", role="admin", password_hash="x")
        cliente = Client(name="C", code="C", is_active=True)
        db.add_all([user, cliente])
        ids = {"site": site.id, "rs": rs.id}
        for code, qty in stock.items():
            p = Product(code=code, name=code, provider="P", presentation="1000",
                        razon_social_id=rs.id, is_active=True)
            db.add(p)
            db.flush()
            stock_service.apply_movement(
                db, site_id=site.id, item=ItemRef("product", p.id), movement_type="receipt",
                quantity=Decimal(qty), user=None,
            )
            ids[code] = p.id
        db.commit()
        ids |= {"user": user.id, "client": cliente.id}
        return ids


def _run(factory, payloads: list[OrderCreate], user_id: int) -> tuple[list[str], list[str]]:
    ok: list[str] = []
    errors: list[str] = []
    barrier = threading.Barrier(len(payloads))

    def worker(payload: OrderCreate) -> None:
        with factory() as db:
            user = db.get(User, user_id)
            barrier.wait()
            try:
                order = order_service.create_order(db, payload, actor=user)
                ok.append(order.operation_number)
            except AppError as exc:
                db.rollback()
                errors.append(exc.code)

    threads = [threading.Thread(target=worker, args=(p,)) for p in payloads]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)
        assert not t.is_alive(), "worker hung (deadlock?)"
    return ok, errors


def _order(ids, base: list[tuple[str, str]], order_type="trabajo") -> OrderCreate:
    extra = {"rework_kind": "own_stock"} if order_type == "retrabajo" else {}
    return OrderCreate(
        order_type=order_type, client_id=ids["client"],
        base_products=[BaseProductIn(product_id=ids[c], liters=Decimal(q)) for c, q in base],
        finished_product_id=ids[base[0][0]], **extra,
    )


def test_concurrent_creates_for_last_liters_exactly_one_succeeds(factory):
    """Trabajo and Retrabajo use different sequence rows, so only the stock
    row lock keeps them from both reserving the last liters."""
    ids = _seed(factory, {"BASE": "100"})
    payloads = [
        _order(ids, [("BASE", "100")], order_type="trabajo" if i % 2 else "retrabajo")
        for i in range(8)
    ]
    ok, errors = _run(factory, payloads, ids["user"])
    assert len(ok) == 1
    assert errors == ["INSUFFICIENT_STOCK"] * 7
    with factory() as db:
        total = sum(
            Decimal(r.quantity)
            for r in db.query(Reservation).filter(Reservation.status == "active")
        )
        assert total == Decimal("100")


def test_concurrent_creates_get_distinct_numbers(factory):
    ids = _seed(factory, {"BASE": "1000"})
    ok, errors = _run(factory, [_order(ids, [("BASE", "1")]) for _ in range(10)], ids["user"])
    assert errors == []
    assert sorted(ok, key=lambda n: int(n.split("-")[1].split()[0])) == [
        f"T-{i} ANB" for i in range(1, 11)
    ]


def test_opposite_product_order_does_not_deadlock(factory):
    """A Trabajo and a Retrabajo (different sequence rows) lock the same two
    products, listed in opposite orders, many times concurrently."""
    ids = _seed(factory, {"A": "1000", "B": "1000"})
    payloads = []
    for i in range(10):
        if i % 2:
            payloads.append(_order(ids, [("A", "1"), ("B", "1")]))
        else:
            payloads.append(_order(ids, [("B", "1"), ("A", "1")], order_type="retrabajo"))
    ok, errors = _run(factory, payloads, ids["user"])
    assert errors == []
    assert len(ok) == 10
    with factory() as db:
        assert db.query(WorkOrder).count() == 10


def test_concurrent_edits_cannot_over_reserve(factory):
    """Edits take no sequence lock: the stock row lock alone serializes them."""
    ids = _seed(factory, {"BASE": "100"})
    with factory() as db:
        user = db.get(User, ids["user"])
        order_ids = [
            order_service.create_order(db, _order(ids, [("BASE", "1")]), actor=user).id
            for _ in range(6)
        ]
    ok: list[int] = []
    errors: list[str] = []
    barrier = threading.Barrier(len(order_ids))

    def worker(order_id: int) -> None:
        with factory() as db:
            user = db.get(User, ids["user"])
            barrier.wait()
            try:
                order_service.update_order(db, order_id, OrderUpdate(
                    base_products=[BaseProductIn(product_id=ids["BASE"], liters=Decimal("90"))]
                ), actor=user)
                ok.append(order_id)
            except AppError as exc:
                db.rollback()
                errors.append(exc.code)

    threads = [threading.Thread(target=worker, args=(i,)) for i in order_ids]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)
    assert len(ok) == 1
    assert errors == ["INSUFFICIENT_STOCK"] * 5
    with factory() as db:
        total = sum(
            Decimal(r.quantity)
            for r in db.query(Reservation).filter(Reservation.status == "active")
        )
        assert total == Decimal("95")  # 90 + 5 x 1
