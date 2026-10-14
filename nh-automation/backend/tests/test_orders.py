"""Phase 2: work orders, numbering, reservations, overselling block, rework,
comments, cancellation, history, print data (BR-1..4, BR-10, BR-16..22)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from app.models.audit_log import AuditLog
from app.models.catalogs import Client, PackagingItem, Product, RazonSocial, Site
from app.models.orders import Reservation, WorkOrder
from app.models.sequences import OrderSequence
from app.services import stock_service
from app.services.stock_service import ItemRef
from tests.conftest import login_as

API = "/api/v1"


# Fixtures ------------------------------------------------------------------------


def _rs(db_session, code: str) -> RazonSocial:
    return db_session.query(RazonSocial).filter(RazonSocial.code == code).one()


def _product(db_session, code, name, presentation, rs_code: str | None, provider="QVR") -> Product:
    p = Product(
        code=code, name=name, provider=provider, presentation=presentation,
        razon_social_id=_rs(db_session, rs_code).id if rs_code else None, is_active=True,
    )
    db_session.add(p)
    db_session.commit()
    return p


@pytest.fixture()
def site(db_session, base_catalogs) -> Site:
    return base_catalogs


@pytest.fixture()
def base_calcio(db_session, base_catalogs) -> Product:
    return _product(db_session, "QVR200C1XL09M01", "BASE CALCIO", "1000", "ANB")


@pytest.fixture()
def nh_calcio(db_session, base_catalogs) -> Product:
    return _product(db_session, "QVR200C1XL20F003", "NH-CALCIO", "1X20", "ANB")


@pytest.fixture()
def nb_neem(db_session, base_catalogs) -> Product:
    return _product(db_session, "GRN100C1XL20F004", "NB-NEEM", "1X20", "NB", provider="GRN")


@pytest.fixture()
def cliente(db_session, base_catalogs) -> Client:
    c = Client(name="Agrícola del Valle", code="AGV", is_active=True)
    db_session.add(c)
    db_session.commit()
    return c


@pytest.fixture()
def envase(db_session, base_catalogs) -> PackagingItem:
    return db_session.query(PackagingItem).filter(PackagingItem.code == "ENVLI20001").one()


def _stock(db_session, site_id: int, item: ItemRef, qty: str) -> None:
    stock_service.apply_movement(
        db_session, site_id=site_id, item=item, movement_type="receipt",
        quantity=Decimal(qty), user=None,
    )
    db_session.commit()


def _available(client, item_type, item_id, site_id) -> dict:
    resp = client.get(
        f"{API}/inventory/availability",
        params={"item_type": item_type, "item_id": item_id, "site_id": site_id},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _payload(client_id, base: list[tuple[int, str]], finished_id, **extra) -> dict:
    data = {
        "order_type": "trabajo",
        "client_id": client_id,
        "base_products": [{"product_id": pid, "liters": liters} for pid, liters in base],
        "finished_product_id": finished_id,
    }
    data.update(extra)
    return data


def _create(client, headers, payload, expected=201) -> dict:
    resp = client.post(f"{API}/orders", json=payload, headers=headers)
    assert resp.status_code == expected, resp.text
    return resp.json()


def _set_status(db_session, order_id: int, status: str, **fields) -> None:
    """Fixture shortcut for statuses phase 2 cannot reach (phase 3 does)."""
    order = db_session.get(WorkOrder, order_id)
    order.status = status
    for k, v in fields.items():
        setattr(order, k, v)
    db_session.commit()


def _active_reservations(db_session, order_id: int) -> dict[tuple[str, int], Decimal]:
    db_session.expire_all()
    rows = db_session.query(Reservation).filter(
        Reservation.order_id == order_id, Reservation.status == "active"
    )
    return {
        (("product", r.product_id) if r.product_id else ("packaging", r.packaging_item_id)):
        Decimal(r.quantity)
        for r in rows
    }


@pytest.fixture()
def calcio_stock(db_session, site, base_calcio):
    _stock(db_session, site.id, ItemRef("product", base_calcio.id), "1500")


# Scenario 1 / BR-1 ------------------------------------------------------------------


def test_create_trabajo_reserves_stock_and_numbers_order(
    client, db_session, site, base_calcio, nh_calcio, cliente, envase, calcio_stock
):
    _stock(db_session, site.id, ItemRef("packaging", envase.id), "100")
    headers = login_as(client, db_session, "admin")
    order = _create(client, headers, _payload(
        cliente.id, [(base_calcio.id, "1000")], nh_calcio.id,
        packaging=[{"packaging_item_id": envase.id, "planned_qty": 50}],
        labels_planned=50, comment="Cambio de envase",
    ))

    assert order["operation_number"] == "T-1 ANB"
    assert order["order_type"] == "trabajo"
    assert order["status"] == "created"
    assert order["expiry_date"] is None and order["expiry_locked"] is False
    assert order["razon_social_code"] == "ANB"
    assert order["site_id"] == site.id  # default site
    assert Decimal(order["finished_liters"]) == Decimal("1000")  # defaults to base sum
    assert order["warnings"] == []
    assert [c["item"] for c in order["checklist"]] == [
        "lote_etiqueta", "niveles_producto", "cantidades", "embalaje"
    ]
    assert not any(c["checked"] for c in order["checklist"])

    avail = _available(client, "product", base_calcio.id, site.id)
    assert Decimal(avail["reserved"]) == Decimal("1000")
    assert Decimal(avail["available"]) == Decimal("500")
    pkg = _available(client, "packaging", envase.id, site.id)
    assert Decimal(pkg["reserved"]) == Decimal("50")

    comments = client.get(f"{API}/orders/{order['id']}/comments").json()
    assert [c["text"] for c in comments] == ["Cambio de envase"]
    assert comments[0]["user_name"] == "Jane Doe"

    holders = client.get(
        f"{API}/inventory/reservations",
        params={"item_type": "product", "item_id": base_calcio.id, "site_id": site.id},
    ).json()
    assert [(h["operation_number"], Decimal(h["quantity"])) for h in holders] == [
        ("T-1 ANB", Decimal("1000"))
    ]

    rows = client.get(f"{API}/inventory", params={"item_type": "product"}).json()["items"]
    row = next(r for r in rows if r["item_id"] == base_calcio.id)
    assert Decimal(row["reserved"]) == Decimal("1000")
    assert Decimal(row["available"]) == Decimal("500")


# Scenario 2 / BR-2 ------------------------------------------------------------------


def test_overselling_blocked_lists_only_short_product(
    client, db_session, site, base_calcio, nh_calcio, nb_neem, cliente, calcio_stock
):
    _stock(db_session, site.id, ItemRef("product", nb_neem.id), "5000")
    headers = login_as(client, db_session, "admin")
    _create(client, headers, _payload(cliente.id, [(base_calcio.id, "1000")], nh_calcio.id))

    resp = client.post(f"{API}/orders", json=_payload(
        cliente.id, [(nb_neem.id, "100"), (base_calcio.id, "800")], nh_calcio.id,
        razon_social_id=_rs(db_session, "ANB").id,
    ), headers=headers)
    assert resp.status_code == 409
    err = resp.json()["error"]
    assert err["code"] == "INSUFFICIENT_STOCK"
    assert err["message"] == (
        "Inventario insuficiente de BASE CALCIO: existencia 1,500.00 L, reservado "
        "1,000.00 L, disponible 500.00 L. Reservado por: T-1 ANB (1,000.00 L)."
    )
    items = err["details"]["items"]
    assert [i["code"] for i in items] == ["QVR200C1XL09M01"]
    assert items[0]["orders"][0]["operation_number"] == "T-1 ANB"

    # Nothing saved and no number consumed.
    db_session.expire_all()
    assert db_session.query(WorkOrder).count() == 1
    seq = db_session.query(OrderSequence).filter(OrderSequence.order_type == "trabajo").one()
    assert seq.next_number == 2
    assert Decimal(_available(client, "product", nb_neem.id, site.id)["reserved"]) == 0


def test_product_without_stock_row_is_blocked(client, db_session, base_calcio, nh_calcio, cliente):
    headers = login_as(client, db_session, "admin")
    resp = client.post(
        f"{API}/orders", json=_payload(cliente.id, [(base_calcio.id, "1")], nh_calcio.id),
        headers=headers,
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "INSUFFICIENT_STOCK"


def test_exact_available_amount_is_allowed(
    client, db_session, base_calcio, nh_calcio, cliente, calcio_stock
):
    headers = login_as(client, db_session, "admin")
    _create(client, headers, _payload(cliente.id, [(base_calcio.id, "1500")], nh_calcio.id))
    resp = client.post(
        f"{API}/orders", json=_payload(cliente.id, [(base_calcio.id, "0.01")], nh_calcio.id),
        headers=headers,
    )
    assert resp.status_code == 409


# BR-19 numbering ---------------------------------------------------------------------


def test_numbering_independent_sequences_shared_by_razones_sociales(
    client, db_session, site, base_calcio, nh_calcio, nb_neem, cliente, calcio_stock
):
    _stock(db_session, site.id, ItemRef("product", nb_neem.id), "1000")
    headers = login_as(client, db_session, "admin")
    t1 = _create(client, headers, _payload(cliente.id, [(nb_neem.id, "10")], nb_neem.id))
    t2 = _create(client, headers, _payload(cliente.id, [(base_calcio.id, "10")], nh_calcio.id))
    r1 = _create(client, headers, {
        "order_type": "retrabajo", "rework_kind": "own_stock",
        "base_products": [{"product_id": nb_neem.id, "liters": "5"}],
        "finished_product_id": nb_neem.id,
    })
    assert [t1["operation_number"], t2["operation_number"], r1["operation_number"]] == [
        "T-1 NB", "T-2 ANB", "R-1 NB"
    ]

    # Deleting leaves a gap: numbers are never reused.
    assert client.delete(f"{API}/orders/{t2['id']}", headers=headers).status_code == 204
    t3 = _create(client, headers, _payload(cliente.id, [(base_calcio.id, "10")], nh_calcio.id))
    assert t3["operation_number"] == "T-3 ANB"


def test_lowered_sequence_cannot_reuse_a_number(
    client, db_session, nb_neem, base_calcio, nh_calcio, site, cliente, calcio_stock
):
    _stock(db_session, site.id, ItemRef("product", nb_neem.id), "1000")
    headers = login_as(client, db_session, "master_admin")
    _create(client, headers, _payload(cliente.id, [(nb_neem.id, "10")], nb_neem.id))  # T-1 NB
    resp = client.patch(f"{API}/order-sequences/trabajo", json={"next_number": 1}, headers=headers)
    assert resp.status_code == 200
    # Same number with another razón social suffix is still refused.
    resp = client.post(
        f"{API}/orders", json=_payload(cliente.id, [(base_calcio.id, "10")], nh_calcio.id),
        headers=headers,
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "SEQUENCE_NUMBER_TAKEN"


# BR-21 order type immutable -------------------------------------------------------------


def test_order_type_and_razon_social_cannot_change_via_patch(
    client, db_session, base_calcio, nh_calcio, cliente, calcio_stock
):
    headers = login_as(client, db_session, "admin")
    order = _create(client, headers, _payload(cliente.id, [(base_calcio.id, "10")], nh_calcio.id))
    url = f"{API}/orders/{order['id']}"

    resp = client.patch(url, json={"order_type": "retrabajo"}, headers=headers)
    assert resp.status_code == 422
    assert resp.json()["error"]["details"]["field"] == "order_type"

    resp = client.patch(url, json={"razon_social_id": _rs(db_session, "NB").id}, headers=headers)
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "IMMUTABLE_FIELD"

    # Sending the unchanged values is harmless.
    resp = client.patch(
        url, json={"order_type": "trabajo", "razon_social_id": order["razon_social_id"]},
        headers=headers,
    )
    assert resp.status_code == 200
    assert client.get(url).json()["order_type"] == "trabajo"


# BR-22 razón social ---------------------------------------------------------------------


def test_razon_social_resolution(
    client, db_session, site, base_calcio, nh_calcio, nb_neem, cliente, calcio_stock
):
    _stock(db_session, site.id, ItemRef("product", nb_neem.id), "1000")
    headers = login_as(client, db_session, "admin")
    mixed = [(nb_neem.id, "600"), (base_calcio.id, "400")]

    resp = client.post(f"{API}/orders", json=_payload(cliente.id, mixed, nh_calcio.id),
                       headers=headers)
    assert resp.status_code == 422
    err = resp.json()["error"]
    assert err["code"] == "RAZON_SOCIAL_REQUIRED"
    assert {o["code"] for o in err["details"]["options"]} == {"NB", "ANB"}

    resp = client.post(f"{API}/orders", json=_payload(
        cliente.id, mixed, nh_calcio.id, razon_social_id=_rs(db_session, "RS3").id
    ), headers=headers)
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "RAZON_SOCIAL_NOT_ALLOWED"

    # Scenario 3: choosing NB.
    order = _create(client, headers, _payload(
        cliente.id, mixed, nh_calcio.id, razon_social_id=_rs(db_session, "NB").id
    ))
    assert order["operation_number"] == "T-1 NB"
    assert Decimal(order["finished_liters"]) == Decimal("1000")
    assert [b["razon_social_code"] for b in order["base_products"]] == ["NB", "ANB"]

    # Edit cannot drop every base product of the order's razón social.
    resp = client.patch(f"{API}/orders/{order['id']}", json={
        "base_products": [{"product_id": base_calcio.id, "liters": "400"}],
    }, headers=headers)
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "RAZON_SOCIAL_MISMATCH"


def test_product_without_razon_social_rejected(client, db_session, site, nh_calcio, cliente):
    orphan = _product(db_session, "IMP001", "IMPORTADO", "1000", None)
    _stock(db_session, site.id, ItemRef("product", orphan.id), "100")
    headers = login_as(client, db_session, "admin")
    resp = client.post(
        f"{API}/orders", json=_payload(cliente.id, [(orphan.id, "10")], nh_calcio.id),
        headers=headers,
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "PRODUCT_WITHOUT_RAZON_SOCIAL"


def test_duplicate_base_product_and_inactive_product_rejected(
    client, db_session, base_calcio, nh_calcio, cliente, calcio_stock
):
    headers = login_as(client, db_session, "admin")
    resp = client.post(f"{API}/orders", json=_payload(
        cliente.id, [(base_calcio.id, "10"), (base_calcio.id, "5")], nh_calcio.id
    ), headers=headers)
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "DUPLICATE_BASE_PRODUCT"

    nh_calcio.is_active = False
    db_session.commit()
    resp = client.post(f"{API}/orders", json=_payload(
        cliente.id, [(base_calcio.id, "10")], nh_calcio.id
    ), headers=headers)
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "INACTIVE_ITEM"


def test_client_required_for_trabajo(client, db_session, base_calcio, nh_calcio, calcio_stock):
    headers = login_as(client, db_session, "admin")
    resp = client.post(f"{API}/orders", json=_payload(
        None, [(base_calcio.id, "10")], nh_calcio.id
    ), headers=headers)
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "CLIENT_REQUIRED"


# BR-20 / BR-21 rework ---------------------------------------------------------------------


def test_rework_previous_order_requires_completed_order_and_copies_expiry(
    client, db_session, base_calcio, nh_calcio, cliente, calcio_stock
):
    headers = login_as(client, db_session, "admin")
    original = _create(
        client, headers, _payload(cliente.id, [(base_calcio.id, "100")], nh_calcio.id)
    )
    rework = {
        "order_type": "retrabajo", "rework_kind": "previous_order",
        "related_order_id": original["id"],
        "base_products": [{"product_id": base_calcio.id, "liters": "50"}],
        "finished_product_id": nh_calcio.id,
    }

    resp = client.post(f"{API}/orders", json=rework, headers=headers)
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "RELATED_ORDER_INVALID"

    resp = client.post(f"{API}/orders", json=rework | {"related_order_id": None},
                       headers=headers)
    assert resp.json()["error"]["code"] == "RELATED_ORDER_REQUIRED"

    # Until phase 3 there are no completed orders: fixture.
    _set_status(db_session, original["id"], "completed", expiry_date=date(2029, 3, 1))
    order = _create(client, headers, rework)
    assert order["operation_number"] == "R-1 ANB"
    assert order["rework_kind"] == "previous_order"
    assert order["related_operation_number"] == "T-1 ANB"
    assert order["client_id"] == cliente.id  # defaulted from the related order
    assert order["expiry_date"] == "2029-03-01"
    assert order["expiry_locked"] is True


def test_rework_own_stock_has_no_client_and_no_expiry(
    client, db_session, base_calcio, nh_calcio, cliente, calcio_stock
):
    """Scenario 4."""
    headers = login_as(client, db_session, "admin")
    order = _create(client, headers, {
        "order_type": "retrabajo", "rework_kind": "own_stock",
        "client_id": cliente.id,  # ignored: own stock has no client
        "base_products": [{"product_id": base_calcio.id, "liters": "100"}],
        "finished_product_id": base_calcio.id,
    })
    assert order["operation_number"] == "R-1 ANB"
    assert order["client_id"] is None
    assert order["expiry_date"] is None and order["expiry_locked"] is False

    resp = client.patch(f"{API}/orders/{order['id']}", json={"order_type": "trabajo"},
                        headers=headers)
    assert resp.status_code == 422

    resp = client.post(f"{API}/orders", json={
        "order_type": "retrabajo",
        "base_products": [{"product_id": base_calcio.id, "liters": "1"}],
        "finished_product_id": base_calcio.id,
    }, headers=headers)
    assert resp.json()["error"]["code"] == "REWORK_KIND_REQUIRED"


# BR-16 editing ---------------------------------------------------------------------------


def test_edit_in_created_rereserves_changed_base_products(
    client, db_session, site, base_calcio, nh_calcio, cliente, calcio_stock
):
    other = _product(db_session, "QVR300", "BASE MAGNESIO", "1000", "ANB")
    _stock(db_session, site.id, ItemRef("product", other.id), "300")
    headers = login_as(client, db_session, "production_manager")
    order = _create(client, headers, _payload(cliente.id, [(base_calcio.id, "1000")], nh_calcio.id))

    # Own reservation is excluded: raising to the full 1,500 L is allowed.
    resp = client.patch(f"{API}/orders/{order['id']}", json={
        "base_products": [
            {"product_id": base_calcio.id, "liters": "1500"},
            {"product_id": other.id, "liters": "200"},
        ],
    }, headers=headers)
    assert resp.status_code == 200, resp.text
    assert _active_reservations(db_session, order["id"]) == {
        ("product", base_calcio.id): Decimal("1500"), ("product", other.id): Decimal("200"),
    }
    assert Decimal(resp.json()["finished_liters"]) == Decimal("1000")  # not sent: kept

    resp = client.patch(f"{API}/orders/{order['id']}", json={
        "base_products": [{"product_id": other.id, "liters": "300"}],
    }, headers=headers)
    assert resp.status_code == 200, resp.text
    assert _active_reservations(db_session, order["id"]) == {("product", other.id): Decimal("300")}
    assert Decimal(_available(client, "product", base_calcio.id, site.id)["reserved"]) == 0

    # Too much: refused, previous reservations untouched.
    resp = client.patch(f"{API}/orders/{order['id']}", json={
        "base_products": [{"product_id": other.id, "liters": "301"}],
    }, headers=headers)
    assert resp.status_code == 409
    assert _active_reservations(db_session, order["id"]) == {("product", other.id): Decimal("300")}

    # Availability for the form excludes the order's own reservations.
    resp = client.get(f"{API}/inventory/availability", params={
        "item_type": "product", "item_id": other.id, "site_id": site.id,
        "exclude_order_id": order["id"],
    })
    assert Decimal(resp.json()["available"]) == Decimal("300")


def test_packaging_only_edit_does_not_recheck_products(
    client, db_session, site, base_calcio, nh_calcio, cliente, envase, calcio_stock
):
    headers = login_as(client, db_session, "admin")
    order = _create(client, headers, _payload(cliente.id, [(base_calcio.id, "1500")], nh_calcio.id))
    # Stock drops below the reservation after creation (e.g. an adjustment).
    stock_service.apply_movement(
        db_session, site_id=site.id, item=ItemRef("product", base_calcio.id),
        movement_type="adjustment", quantity=Decimal("-600"), user=None,
    )
    db_session.commit()
    resp = client.patch(f"{API}/orders/{order['id']}", json={
        "packaging": [{"packaging_item_id": envase.id, "planned_qty": 10}],
        "labels_planned": 10,
    }, headers=headers)
    assert resp.status_code == 200, resp.text
    assert _active_reservations(db_session, order["id"]) == {
        ("product", base_calcio.id): Decimal("1500"), ("packaging", envase.id): Decimal("10"),
    }


@pytest.mark.parametrize("status", ["in_progress", "paused", "completed", "closed", "cancelled"])
def test_edit_refused_once_production_started(
    client, db_session, base_calcio, nh_calcio, cliente, calcio_stock, status
):
    headers = login_as(client, db_session, "admin")
    order = _create(client, headers, _payload(cliente.id, [(base_calcio.id, "10")], nh_calcio.id))
    _set_status(db_session, order["id"], status)
    resp = client.patch(f"{API}/orders/{order['id']}", json={"labels_planned": 3},
                        headers=headers)
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "ORDER_NOT_EDITABLE"
    # Comments are still allowed.
    resp = client.post(f"{API}/orders/{order['id']}/comments", json={"text": "Revisado"},
                       headers=headers)
    assert resp.status_code == 201


def test_snapshots_preserved_after_product_rename(
    client, db_session, base_calcio, nh_calcio, cliente, calcio_stock
):
    headers = login_as(client, db_session, "admin")
    order = _create(client, headers, _payload(cliente.id, [(base_calcio.id, "10")], nh_calcio.id))
    resp = client.patch(f"{API}/products/{base_calcio.id}", json={"name": "BASE CALCIO V2"},
                        headers=headers)
    assert resp.status_code == 200
    resp = client.patch(f"{API}/products/{nh_calcio.id}", json={"presentation": "1X10"},
                        headers=headers)
    assert resp.status_code == 200

    # An unrelated edit keeps the original snapshots too.
    client.patch(f"{API}/orders/{order['id']}", json={
        "base_products": [{"product_id": base_calcio.id, "liters": "12"}],
    }, headers=headers)
    data = client.get(f"{API}/orders/{order['id']}").json()
    assert data["base_products"][0]["name"] == "BASE CALCIO"
    assert Decimal(data["base_products"][0]["liters"]) == Decimal("12")
    assert data["finished_presentation"] == "1X20"


# Scenario 5: comments and history ------------------------------------------------------


def test_production_manager_edits_and_comments_with_authorship(
    client, db_session, base_calcio, nh_calcio, cliente, envase, calcio_stock
):
    headers = login_as(client, db_session, "admin")
    order = _create(client, headers, _payload(cliente.id, [(base_calcio.id, "1000")], nh_calcio.id))
    url = f"{API}/orders/{order['id']}"

    headers = login_as(client, db_session, "production_manager")
    assert client.patch(url, json={"comment": "Cambio de etiqueta"},
                        headers=headers).status_code == 200
    assert client.patch(url, json={
        "packaging": [{"packaging_item_id": envase.id, "planned_qty": 50}],
    }, headers=headers).status_code == 200
    resp = client.post(f"{url}/comments", json={"text": "  Vaciar porrón  "}, headers=headers)
    assert resp.status_code == 201
    assert resp.json()["text"] == "Vaciar porrón"

    comments = client.get(f"{url}/comments").json()
    assert [c["text"] for c in comments] == ["Vaciar porrón", "Cambio de etiqueta"]
    assert {c["user_name"] for c in comments} == {"Jane Doe"}

    history = client.get(f"{url}/history").json()
    assert [h["action"] for h in history] == ["comment", "update", "comment", "create"]
    assert all(h["user_name"] for h in history)
    update = history[1]
    assert update["before"]["packaging"] == []
    assert update["after"]["packaging"] == [{"packaging_item_id": envase.id, "planned_qty": 50}]


def test_comments_any_status(
    client, db_session, base_calcio, nh_calcio, cliente, calcio_stock
):
    headers = login_as(client, db_session, "admin")
    order = _create(client, headers, _payload(cliente.id, [(base_calcio.id, "10")], nh_calcio.id))
    url = f"{API}/orders/{order['id']}/comments"
    for status in ("cancelled", "closed"):
        _set_status(db_session, order["id"], status)
        for role in ("admin", "production_manager", "master_admin"):
            headers = login_as(client, db_session, role)
            assert client.post(url, json={"text": f"{role} {status}"},
                               headers=headers).status_code == 201

    headers = login_as(client, db_session, "admin")
    assert client.post(url, json={"text": "   "}, headers=headers).status_code == 422


# BR-10 / BR-17 cancel and delete -------------------------------------------------------------


def test_cancel_releases_reservations_and_needs_reason(
    client, db_session, site, base_calcio, nh_calcio, cliente, envase, calcio_stock
):
    headers = login_as(client, db_session, "admin")
    order = _create(client, headers, _payload(
        cliente.id, [(base_calcio.id, "1000")], nh_calcio.id,
        packaging=[{"packaging_item_id": envase.id, "planned_qty": 5}],
    ))
    url = f"{API}/orders/{order['id']}/cancel"

    headers = login_as(client, db_session, "production_manager")
    assert client.post(url, json={"reason": " "}, headers=headers).status_code == 422
    resp = client.post(url, json={"reason": "El cliente canceló"}, headers=headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["status"] == "cancelled"
    assert data["cancel_reason"] == "El cliente canceló"
    assert data["cancelled_by_name"] == "Jane Doe"
    assert data["can_edit"] is False and data["can_cancel"] is False

    assert _active_reservations(db_session, order["id"]) == {}
    assert Decimal(_available(client, "product", base_calcio.id, site.id)["available"]) == 1500
    assert Decimal(_available(client, "packaging", envase.id, site.id)["reserved"]) == 0

    resp = client.post(url, json={"reason": "otra vez"}, headers=headers)
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "INVALID_TRANSITION"
    resp = client.delete(f"{API}/orders/{order['id']}", headers=headers)
    assert resp.status_code == 409


@pytest.mark.parametrize("status", ["in_progress", "completed", "closed"])
def test_cancel_refused_after_production_started(
    client, db_session, base_calcio, nh_calcio, cliente, calcio_stock, status
):
    headers = login_as(client, db_session, "admin")
    order = _create(client, headers, _payload(cliente.id, [(base_calcio.id, "10")], nh_calcio.id))
    _set_status(db_session, order["id"], status)
    resp = client.post(f"{API}/orders/{order['id']}/cancel", json={"reason": "x"},
                       headers=headers)
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "INVALID_TRANSITION"


def test_delete_releases_reservations(
    client, db_session, site, base_calcio, nh_calcio, cliente, calcio_stock
):
    headers = login_as(client, db_session, "admin")
    order = _create(client, headers, _payload(cliente.id, [(base_calcio.id, "1000")], nh_calcio.id))
    headers = login_as(client, db_session, "production_manager")
    assert client.delete(f"{API}/orders/{order['id']}", headers=headers).status_code == 204
    assert client.get(f"{API}/orders/{order['id']}").status_code == 404
    assert Decimal(_available(client, "product", base_calcio.id, site.id)["reserved"]) == 0
    db_session.expire_all()
    assert db_session.query(Reservation).count() == 0


# Scenario 6 / BR-4 packaging warning ------------------------------------------------------


def test_packaging_shortage_is_a_warning(
    client, db_session, site, base_calcio, nh_calcio, cliente, envase, calcio_stock
):
    _stock(db_session, site.id, ItemRef("packaging", envase.id), "10")
    headers = login_as(client, db_session, "admin")
    order = _create(client, headers, _payload(
        cliente.id, [(base_calcio.id, "1000")], nh_calcio.id,
        packaging=[{"packaging_item_id": envase.id, "planned_qty": 50}],
    ))
    assert order["warnings"] == [{
        "type": "packaging_shortage", "packaging_item_id": envase.id, "code": "ENVLI20001",
        "description": envase.description, "planned": 50, "available": 10,
    }]
    pkg = _available(client, "packaging", envase.id, site.id)
    assert Decimal(pkg["reserved"]) == 50 and Decimal(pkg["available"]) == -40

    # Lowering the planned quantity clears the warning on edit.
    resp = client.patch(f"{API}/orders/{order['id']}", json={
        "packaging": [{"packaging_item_id": envase.id, "planned_qty": 10}],
    }, headers=headers)
    assert resp.json()["warnings"] == []


# BR-18 audit --------------------------------------------------------------------------------


def test_audit_log_records_every_order_action(
    client, db_session, base_calcio, nh_calcio, cliente, calcio_stock
):
    headers = login_as(client, db_session, "admin")
    a = _create(client, headers, _payload(cliente.id, [(base_calcio.id, "10")], nh_calcio.id,
                                          comment="Primero"))
    b = _create(client, headers, _payload(cliente.id, [(base_calcio.id, "10")], nh_calcio.id))
    client.patch(f"{API}/orders/{a['id']}", json={"labels_planned": 7}, headers=headers)
    client.post(f"{API}/orders/{a['id']}/cancel", json={"reason": "r"}, headers=headers)
    client.delete(f"{API}/orders/{b['id']}", headers=headers)

    db_session.expire_all()
    rows = db_session.query(AuditLog).filter(AuditLog.entity == "work_order").all()
    actions = {(r.entity_id, r.action) for r in rows}
    assert actions == {
        (a["id"], "create"), (a["id"], "comment"), (a["id"], "update"), (a["id"], "cancel"),
        (b["id"], "create"), (b["id"], "delete"),
    }
    update = next(r for r in rows if r.action == "update")
    assert update.before["labels_planned"] is None and update.after["labels_planned"] == 7
    delete = next(r for r in rows if r.action == "delete")
    assert delete.before["operation_number"] == b["operation_number"]
    # A no-op edit writes nothing.
    last_id = db_session.query(AuditLog.id).order_by(AuditLog.id.desc()).first()[0]
    resp = client.patch(f"{API}/orders/{a['id']}", json={}, headers=headers)
    assert resp.status_code == 409  # a is cancelled
    c = _create(client, headers, _payload(cliente.id, [(base_calcio.id, "10")], nh_calcio.id))
    assert client.patch(f"{API}/orders/{c['id']}", json={"labels_planned": None},
                        headers=headers).status_code == 200
    db_session.expire_all()
    new = db_session.query(AuditLog).filter(
        AuditLog.entity == "work_order", AuditLog.id > last_id
    ).all()
    assert [r.action for r in new] == ["create"]


# Scenario 7 print data ------------------------------------------------------------------------


def test_print_data_lists_all_base_products(
    client, db_session, site, base_calcio, nh_calcio, nb_neem, cliente, calcio_stock
):
    _stock(db_session, site.id, ItemRef("product", nb_neem.id), "1000")
    headers = login_as(client, db_session, "admin")
    order = _create(client, headers, _payload(
        cliente.id, [(base_calcio.id, "400"), (nb_neem.id, "600")], nh_calcio.id,
        razon_social_id=_rs(db_session, "ANB").id, comment="Uno", barcode_mode="per_box",
    ))
    client.post(f"{API}/orders/{order['id']}/comments", json={"text": "Dos"}, headers=headers)
    data = client.get(f"{API}/orders/{order['id']}/print-data").json()
    assert data["order"]["order_type"] == "trabajo"
    assert [b["code"] for b in data["order"]["base_products"]] == [
        "QVR200C1XL09M01", "GRN100C1XL20F004"
    ]
    assert [c["text"] for c in data["comments"]] == ["Uno", "Dos"]  # paper order
    assert data["created"]["name"] == "Jane Doe"
    assert data["assigned"] is None and data["closed"] is None
    assert data["barcodes"] == {
        "operation_number": "T-1 ANB", "finished_code": "QVR200C1XL20F003"
    }


# FR-ORD-2 list filters ---------------------------------------------------------------------


def test_list_filters_and_search(
    client, db_session, site, base_calcio, nh_calcio, nb_neem, cliente, calcio_stock
):
    _stock(db_session, site.id, ItemRef("product", nb_neem.id), "1000")
    other_client = Client(name="Otro", code="OTR", is_active=True)
    db_session.add(other_client)
    db_session.commit()
    headers = login_as(client, db_session, "admin")
    t1 = _create(client, headers, _payload(cliente.id, [(base_calcio.id, "10")], nh_calcio.id,
                                           order_date="2026-10-01"))
    t2 = _create(client, headers, _payload(other_client.id, [(nb_neem.id, "10")], nb_neem.id,
                                           order_date="2026-10-05"))
    r1 = _create(client, headers, {
        "order_type": "retrabajo", "rework_kind": "own_stock",
        "base_products": [{"product_id": nb_neem.id, "liters": "5"}],
        "finished_product_id": nh_calcio.id, "order_date": "2026-10-09",
    })
    client.post(f"{API}/orders/{t2['id']}/cancel", json={"reason": "r"}, headers=headers)

    def ids(**params) -> list[int]:
        resp = client.get(f"{API}/orders", params=params)
        assert resp.status_code == 200, resp.text
        return [o["id"] for o in resp.json()["items"]]

    assert ids() == [r1["id"], t2["id"], t1["id"]]  # newest first
    assert ids(status="cancelled") == [t2["id"]]
    assert ids(status="created,cancelled") == [r1["id"], t2["id"], t1["id"]]
    assert ids(order_type="retrabajo") == [r1["id"]]
    assert ids(client_id=cliente.id) == [t1["id"]]
    assert ids(razon_social_id=_rs(db_session, "NB").id) == [r1["id"], t2["id"]]
    assert ids(product_id=nh_calcio.id) == [r1["id"], t1["id"]]  # finished product
    assert ids(product_id=nb_neem.id) == [r1["id"], t2["id"]]  # base or finished
    assert ids(date_from="2026-10-02", date_to="2026-10-05") == [t2["id"]]
    assert ids(search="r-1") == [r1["id"]]
    assert ids(site_id=site.id) == [r1["id"], t2["id"], t1["id"]]
    item = client.get(f"{API}/orders", params={"search": "T-1"}).json()["items"][0]
    assert item["base_products"] == ["QVR200C1XL09M01 — BASE CALCIO"]
    assert item["client_name"] == "Agrícola del Valle"


# Phase 1b leftover: razón social code locked once used ---------------------------------------


def test_razon_social_code_locked_once_used_by_an_order(
    client, db_session, base_calcio, nh_calcio, cliente, calcio_stock
):
    headers = login_as(client, db_session, "admin")
    anb = _rs(db_session, "ANB")
    _create(client, headers, _payload(cliente.id, [(base_calcio.id, "10")], nh_calcio.id))
    resp = client.patch(f"{API}/razones-sociales/{anb.id}", json={"code": "AGB"}, headers=headers)
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "RAZON_SOCIAL_IN_USE"
    resp = client.patch(f"{API}/razones-sociales/{anb.id}", json={"name": "AGRONB SA"},
                        headers=headers)
    assert resp.status_code == 200


def test_missing_order_message_uses_feminine_form(client, db_session, base_catalogs):
    login_as(client, db_session, "admin")
    resp = client.get(f"{API}/orders/999999")
    assert resp.status_code == 404
    assert resp.json()["error"]["message"] == "Orden no encontrada."
