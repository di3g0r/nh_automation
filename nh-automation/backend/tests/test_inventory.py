"""Inventory (FR-INV): receipts, adjustments, movements, availability, alerts, concurrency."""

from __future__ import annotations

import os
import threading
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, func
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.models.audit_log import AuditLog
from app.models.catalogs import PackagingItem, Product, Site
from app.models.stock import StockLevel, StockMovement
from app.services import stock_service
from app.services.stock_service import ItemRef
from tests.conftest import login_as

API = "/api/v1"


@pytest.fixture()
def product(db_session, base_catalogs) -> Product:
    p = Product(
        code="QVR200C1XL09M01", name="BASE CALCIO", provider="QVR", presentation="1000",
        is_active=True,
    )
    db_session.add(p)
    db_session.commit()
    return p


@pytest.fixture()
def envase(db_session, base_catalogs) -> PackagingItem:
    return db_session.query(PackagingItem).filter(PackagingItem.code == "ENVLI20001").one()


def _receipt(client, headers, site_id, item_id, quantity, item_type="product", note=None):
    return client.post(
        f"{API}/inventory/receipts",
        json={
            "item_type": item_type, "item_id": item_id, "site_id": site_id,
            "quantity": quantity, "note": note,
        },
        headers=headers,
    )


def _on_hand(client, item_type, item_id, site_id) -> Decimal:
    resp = client.get(
        f"{API}/inventory/availability",
        params={"item_type": item_type, "item_id": item_id, "site_id": site_id},
    )
    assert resp.status_code == 200
    return Decimal(resp.json()["on_hand"])


def test_receipt_creates_movement_and_updates_on_hand(client, db_session, product, base_catalogs):
    headers = login_as(client, db_session, "supervisor")
    resp = _receipt(client, headers, base_catalogs.id, product.id, "1000.50", note="Proveedor")
    assert resp.status_code == 201
    body = resp.json()
    assert body["type"] == "receipt"
    assert body["quantity"] == "1000.50"
    assert body["item_code"] == "QVR200C1XL09M01"
    assert body["user_name"] == "Jane Doe"

    _receipt(client, headers, base_catalogs.id, product.id, "500")
    assert _on_hand(client, "product", product.id, base_catalogs.id) == Decimal("1500.50")

    avail = client.get(
        f"{API}/inventory/availability",
        params={"item_type": "product", "item_id": product.id, "site_id": base_catalogs.id},
    ).json()
    assert Decimal(avail["reserved"]) == 0
    assert Decimal(avail["available"]) == Decimal("1500.50")

    audit = db_session.query(AuditLog).filter(AuditLog.entity == "stock").all()
    assert [a.action for a in audit] == ["receipt", "receipt"]
    assert audit[0].after["on_hand"] == "1000.50"


def test_receipt_quantity_must_be_positive(client, db_session, product, base_catalogs):
    headers = login_as(client, db_session, "admin")
    assert _receipt(client, headers, base_catalogs.id, product.id, "0").status_code == 422
    assert _receipt(client, headers, base_catalogs.id, product.id, "-5").status_code == 422
    assert _receipt(client, headers, base_catalogs.id, product.id, "1.234").status_code == 422


def test_packaging_quantities_are_whole_units(client, db_session, envase, base_catalogs):
    headers = login_as(client, db_session, "admin")
    resp = _receipt(client, headers, base_catalogs.id, envase.id, "10.5", item_type="packaging")
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "INVALID_QUANTITY"
    resp = _receipt(client, headers, base_catalogs.id, envase.id, "10", item_type="packaging")
    assert resp.status_code == 201


def test_receipt_on_inactive_item_rejected(client, db_session, product, base_catalogs):
    headers = login_as(client, db_session, "admin")
    product.is_active = False
    db_session.commit()
    resp = _receipt(client, headers, base_catalogs.id, product.id, "10")
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "INACTIVE_ITEM"


def test_adjustment_computes_delta_and_requires_reason(client, db_session, product, base_catalogs):
    headers = login_as(client, db_session, "supervisor")
    _receipt(client, headers, base_catalogs.id, product.id, "100")

    payload = {
        "item_type": "product", "item_id": product.id, "site_id": base_catalogs.id,
        "counted_quantity": "92.5",
    }
    # Reason is mandatory (missing and blank).
    resp = client.post(f"{API}/inventory/adjustments", json=payload, headers=headers)
    assert resp.status_code == 422
    resp = client.post(
        f"{API}/inventory/adjustments", json=payload | {"reason": "   "}, headers=headers
    )
    assert resp.status_code == 422

    resp = client.post(
        f"{API}/inventory/adjustments", json=payload | {"reason": "Conteo físico"}, headers=headers
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["type"] == "adjustment"
    assert Decimal(body["quantity"]) == Decimal("-7.50")
    assert body["note"] == "Conteo físico"
    assert _on_hand(client, "product", product.id, base_catalogs.id) == Decimal("92.50")

    # Same count again -> nothing to adjust.
    resp = client.post(
        f"{API}/inventory/adjustments", json=payload | {"reason": "otra vez"}, headers=headers
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "ADJUSTMENT_NO_CHANGE"


def test_on_hand_equals_sum_of_movements(client, db_session, product, base_catalogs):
    headers = login_as(client, db_session, "admin")
    for q in ("10", "20.25", "5"):
        _receipt(client, headers, base_catalogs.id, product.id, q)
    client.post(
        f"{API}/inventory/adjustments",
        json={"item_type": "product", "item_id": product.id, "site_id": base_catalogs.id,
              "counted_quantity": "30", "reason": "conteo"},
        headers=headers,
    )
    total = db_session.query(func.sum(StockMovement.quantity)).scalar()
    level = db_session.query(StockLevel).one()
    assert Decimal(level.on_hand) == Decimal(total) == Decimal("30")


def test_movements_list_filters(client, db_session, product, envase, base_catalogs):
    headers = login_as(client, db_session, "admin")
    _receipt(client, headers, base_catalogs.id, product.id, "10")
    _receipt(client, headers, base_catalogs.id, envase.id, "5", item_type="packaging")
    client.post(
        f"{API}/inventory/adjustments",
        json={"item_type": "product", "item_id": product.id, "site_id": base_catalogs.id,
              "counted_quantity": "8", "reason": "merma"},
        headers=headers,
    )

    all_rows = client.get(f"{API}/inventory/movements").json()
    assert all_rows["total"] == 3
    assert all_rows["items"][0]["type"] == "adjustment"  # newest first

    assert client.get(f"{API}/inventory/movements?type=receipt").json()["total"] == 2
    by_item = client.get(
        f"{API}/inventory/movements", params={"item_type": "packaging", "item_id": envase.id}
    ).json()
    assert by_item["total"] == 1 and by_item["items"][0]["item_code"] == "ENVLI20001"
    assert client.get(f"{API}/inventory/movements?item_type=product").json()["total"] == 2

    user_id = all_rows["items"][0]["user_id"]
    users = client.get(f"{API}/inventory/movement-users").json()
    assert users == [{"id": user_id, "full_name": "Jane Doe"}]
    assert client.get(f"{API}/inventory/movements?user_id={user_id}").json()["total"] == 3
    assert client.get(f"{API}/inventory/movements?user_id=9999").json()["total"] == 0

    # Local-day date filter: everything happened "today" (America/Mazatlan).
    from app.core.timezone import local_today

    today = local_today().isoformat()
    in_range = client.get(
        f"{API}/inventory/movements", params={"date_from": today, "date_to": today}
    ).json()
    assert in_range["total"] == 3
    assert client.get(
        f"{API}/inventory/movements", params={"date_from": "2000-01-01", "date_to": "2000-01-02"}
    ).json()["total"] == 0


def test_inventory_list_shows_items_without_stock(client, db_session, product, base_catalogs):
    login_as(client, db_session, "supervisor")
    rows = client.get(f"{API}/inventory?item_type=product").json()
    assert rows["total"] == 1
    row = rows["items"][0]
    assert row["code"] == product.code
    assert Decimal(row["on_hand"]) == 0
    assert Decimal(row["reserved"]) == 0  # reservations arrive in phase 2
    assert Decimal(row["available"]) == 0

    packaging = client.get(f"{API}/inventory?item_type=packaging&category=caja").json()
    assert packaging["total"] == 7
    search = client.get(f"{API}/inventory?item_type=packaging&search=Fisher").json()
    assert search["total"] == 2


def test_low_stock_alert(client, db_session, envase, base_catalogs):
    headers = login_as(client, db_session, "admin")
    client.patch(
        f"{API}/packaging-items/{envase.id}", json={"low_stock_threshold": 100}, headers=headers
    )
    _receipt(client, headers, base_catalogs.id, envase.id, "99", item_type="packaging")

    alerts = client.get(f"{API}/inventory/alerts").json()
    assert [a["code"] for a in alerts["low_stock"]] == ["ENVLI20001"]
    assert alerts["count"] == 1
    low = client.get(f"{API}/inventory?item_type=packaging&low_stock=true").json()
    assert [r["code"] for r in low["items"]] == ["ENVLI20001"]
    assert low["items"][0]["low_stock"] is True

    # At the threshold is not "below" it.
    _receipt(client, headers, base_catalogs.id, envase.id, "1", item_type="packaging")
    assert client.get(f"{API}/inventory/alerts").json()["low_stock"] == []

    # Inactive items do not alert for low stock.
    _receipt(client, headers, base_catalogs.id, envase.id, "1", item_type="packaging")
    client.patch(
        f"{API}/packaging-items/{envase.id}", json={"low_stock_threshold": 500}, headers=headers
    )
    assert len(client.get(f"{API}/inventory/alerts").json()["low_stock"]) == 1
    client.patch(f"{API}/packaging-items/{envase.id}", json={"is_active": False}, headers=headers)
    assert client.get(f"{API}/inventory/alerts").json()["low_stock"] == []


def test_negative_stock_alert(client, db_session, product, base_catalogs):
    login_as(client, db_session, "admin")
    # Consumption (phase 3) may push stock negative (BR-9); simulate it directly.
    stock_service.apply_movement(
        db_session, site_id=base_catalogs.id, item=ItemRef("product", product.id),
        movement_type="consumption", quantity=Decimal("-12.5"), user=None,
    )
    db_session.commit()

    alerts = client.get(f"{API}/inventory/alerts").json()
    assert len(alerts["negative_stock"]) == 1
    neg = alerts["negative_stock"][0]
    assert neg["code"] == product.code and Decimal(neg["on_hand"]) == Decimal("-12.5")
    rows = client.get(f"{API}/inventory?item_type=product&negative=true").json()
    assert rows["total"] == 1 and rows["items"][0]["negative"] is True


def test_stock_is_per_site(client, db_session, product, base_catalogs):
    headers = login_as(client, db_session, "admin")
    other = client.post(f"{API}/sites", json={"name": "Planta 2"}, headers=headers).json()
    _receipt(client, headers, base_catalogs.id, product.id, "10")
    _receipt(client, headers, other["id"], product.id, "3")
    assert _on_hand(client, "product", product.id, base_catalogs.id) == Decimal("10")
    assert _on_hand(client, "product", product.id, other["id"]) == Decimal("3")
    assert client.get(f"{API}/inventory?item_type=product").json()["total"] == 2
    assert client.get(
        f"{API}/inventory?item_type=product&site_id={other['id']}"
    ).json()["total"] == 1


# Concurrency (BR-3 / BR-5) ---------------------------------------------------


def _run_concurrent_receipts(session_factory, site_id: int, product_id: int, n: int) -> None:
    errors: list[BaseException] = []
    barrier = threading.Barrier(n)

    def worker() -> None:
        db = session_factory()
        try:
            barrier.wait()
            stock_service.apply_movement(
                db, site_id=site_id, item=ItemRef("product", product_id),
                movement_type="receipt", quantity=Decimal("1.25"), user=None,
            )
            db.commit()
        except BaseException as exc:  # pragma: no cover - reported below
            errors.append(exc)
        finally:
            db.close()

    threads = [threading.Thread(target=worker) for _ in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []


def _assert_consistent(session_factory, n: int) -> None:
    db = session_factory()
    try:
        levels = db.query(StockLevel).all()
        assert len(levels) == 1  # no duplicate rows from the create race
        total = db.query(func.sum(StockMovement.quantity)).scalar()
        assert db.query(StockMovement).count() == n
        assert Decimal(levels[0].on_hand) == Decimal(total) == Decimal("1.25") * n
    finally:
        db.close()


def _seed_minimal(session_factory) -> tuple[int, int]:
    db = session_factory()
    site = Site(name="S", is_default=True, is_active=True)
    product = Product(code="P", name="P", provider="X", presentation="1", is_active=True)
    db.add_all([site, product])
    db.commit()
    ids = site.id, product.id
    db.close()
    return ids


def test_concurrent_movements_keep_totals_consistent(tmp_path):
    """File-based SQLite with real threads: the atomic increment + create-race
    handling keep on_hand == sum(movements)."""
    engine = create_engine(
        f"sqlite+pysqlite:///{tmp_path / 'concurrency.db'}",
        connect_args={"check_same_thread": False, "timeout": 30},
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False)
    site_id, product_id = _seed_minimal(factory)
    _run_concurrent_receipts(factory, site_id, product_id, n=12)
    _assert_consistent(factory, n=12)
    engine.dispose()


@pytest.mark.skipif(
    not os.environ.get("TEST_POSTGRES_URL"),
    reason="set TEST_POSTGRES_URL to an empty scratch Postgres DB to run",
)
def test_concurrent_movements_postgres():
    """Same check on real PostgreSQL, where SELECT ... FOR UPDATE is enforced."""
    engine = create_engine(os.environ["TEST_POSTGRES_URL"])
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    try:
        factory = sessionmaker(bind=engine, autoflush=False)
        site_id, product_id = _seed_minimal(factory)
        _run_concurrent_receipts(factory, site_id, product_id, n=20)
        _assert_consistent(factory, n=20)
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()
