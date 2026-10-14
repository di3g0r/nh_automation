"""Phase 3: expiry, machine assignment and split, queues, production controls,
completion stock movements, differences, traceability, closing, machine board
(BR-7..12, BR-14, BR-16, BR-17, BR-20, BR-23, BR-24) and acceptance scenarios."""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.models.assignments import Assignment, AssignmentEvent
from app.models.audit_log import AuditLog
from app.models.catalogs import Client, Machine, PackagingItem, Product, RazonSocial, Site
from app.models.orders import Reservation, WorkOrder
from app.models.stock import StockMovement
from app.services import stock_service
from app.services.stock_service import ItemRef
from tests.conftest import login_as

API = "/api/v1"


# Fixtures ------------------------------------------------------------------------------


def _rs(db_session, code: str) -> RazonSocial:
    return db_session.query(RazonSocial).filter(RazonSocial.code == code).one()


def _product(db_session, code, name, presentation, rs_code, provider="QVR") -> Product:
    p = Product(
        code=code, name=name, provider=provider, presentation=presentation,
        razon_social_id=_rs(db_session, rs_code).id, is_active=True,
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


@pytest.fixture()
def machines(db_session, site) -> dict[str, Machine]:
    out = {}
    for n in range(1, 7):
        m = Machine(code=f"M{n:02d}", name=f"Máquina {n}", site_id=site.id, is_active=True,
                    in_maintenance=False)
        db_session.add(m)
        out[m.code] = m
    db_session.commit()
    return out


def _stock(db_session, site_id: int, item: ItemRef, qty: str) -> None:
    stock_service.apply_movement(
        db_session, site_id=site_id, item=item, movement_type="receipt",
        quantity=Decimal(qty), user=None,
    )
    db_session.commit()


def _on_hand(db_session, site_id: int, item: ItemRef) -> Decimal:
    db_session.expire_all()
    return stock_service.get_on_hand(db_session, site_id, item)


def _create(client, headers, client_id, base, finished_id, expected=201, **extra) -> dict:
    payload = {
        "order_type": "trabajo",
        "client_id": client_id,
        "base_products": [{"product_id": pid, "liters": liters} for pid, liters in base],
        "finished_product_id": finished_id,
    }
    payload.update(extra)
    resp = client.post(f"{API}/orders", json=payload, headers=headers)
    assert resp.status_code == expected, resp.text
    return resp.json()


def _expiry(client, headers, order_id, value, expected=200) -> dict:
    resp = client.put(f"{API}/orders/{order_id}/expiry", json={"expiry_date": value},
                      headers=headers)
    assert resp.status_code == expected, resp.text
    return resp.json()


def _assign(client, headers, order_id, split, expected=200) -> dict:
    resp = client.put(
        f"{API}/orders/{order_id}/assignments",
        json={"assignments": [{"machine_id": m.id, "planned_liters": liters}
                              for m, liters in split]},
        headers=headers,
    )
    assert resp.status_code == expected, resp.text
    return resp.json()


def _act(client, headers, assignment_id, action, expected=200, **body) -> dict:
    resp = client.post(f"{API}/assignments/{assignment_id}/{action}", json=body or None,
                       headers=headers)
    assert resp.status_code == expected, resp.text
    return resp.json()


def _order(client, order_id) -> dict:
    resp = client.get(f"{API}/orders/{order_id}")
    assert resp.status_code == 200, resp.text
    return resp.json()


def _by_machine(order: dict) -> dict[str, dict]:
    return {a["machine_code"]: a for a in order["assignments"]}


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


@pytest.fixture()
def jefe(client, db_session):
    return login_as(client, db_session, "production_manager")


def _ready_order(client, db_session, headers, cliente, base_calcio, nh_calcio, machines,
                 liters="100", split=None) -> dict:
    """An Asignada order: expiry set and the split adding up."""
    order = _create(client, headers, cliente.id, [(base_calcio.id, liters)], nh_calcio.id)
    _expiry(client, headers, order["id"], "2029-03-01")
    split = split or [(machines["M01"], "70"), (machines["M04"], "30")]
    return _assign(client, headers, order["id"], split)


# Scenario 1 / BR-7 / BR-20 -----------------------------------------------------------------


def test_scenario1_expiry_and_split_make_order_assigned(
    client, db_session, cliente, base_calcio, nh_calcio, machines, calcio_stock, jefe
):
    order = _create(client, jefe, cliente.id, [(base_calcio.id, "100")], nh_calcio.id)
    assert order["operation_number"] == "T-1 ANB"
    resp = client.get(f"{API}/production/to-assign")
    row = next(r for r in resp.json() if r["id"] == order["id"])
    assert row["missing"] == ["expiry", "machines"]

    # Any day is stored as the 1st of the month (shown MM/AAAA).
    data = _expiry(client, jefe, order["id"], "2029-03-17")
    assert data["expiry_date"] == "2029-03-01"
    assert data["expiry_set_by_name"] == "Jane Doe"
    assert data["status"] == "created"
    assert data["missing_for_assign"] == ["machines"]

    # 70 + 20 refused; 70 + 40 refused; nothing saved.
    for bad in ("20", "40"):
        resp = client.put(
            f"{API}/orders/{order['id']}/assignments",
            json={"assignments": [
                {"machine_id": machines["M01"].id, "planned_liters": "70"},
                {"machine_id": machines["M04"].id, "planned_liters": bad},
            ]},
            headers=jefe,
        )
        assert resp.status_code == 422
        assert resp.json()["error"]["code"] == "SPLIT_MISMATCH"
    assert _order(client, order["id"])["assignments"] == []

    data = _assign(client, jefe, order["id"], [(machines["M01"], "70"), (machines["M04"], "30")])
    assert data["status"] == "assigned"
    assert data["assigned_liters"] == "100.00"
    assert {a["machine_code"]: a["planned_liters"] for a in data["assignments"]} == {
        "M01": "70.00", "M04": "30.00",
    }
    assert all(a["status"] == "pending" for a in data["assignments"])
    in_prod = client.get(f"{API}/production/in-production").json()
    assert [r["id"] for r in in_prod] == [order["id"]]
    assert client.get(f"{API}/production/to-assign").json() == []


def test_split_validation(client, db_session, cliente, base_calcio, nh_calcio, machines,
                          calcio_stock, jefe):
    order = _create(client, jefe, cliente.id, [(base_calcio.id, "100")], nh_calcio.id)
    oid = order["id"]
    url = f"{API}/orders/{oid}/assignments"
    m1, m2 = machines["M01"], machines["M02"]
    dup = {"assignments": [{"machine_id": m1.id, "planned_liters": "50"},
                           {"machine_id": m1.id, "planned_liters": "50"}]}
    assert client.put(url, json=dup, headers=jefe).json()["error"]["code"] == "DUPLICATE_MACHINE"
    zero = {"assignments": [{"machine_id": m1.id, "planned_liters": "0"}]}
    assert client.put(url, json=zero, headers=jefe).status_code == 422
    m2.in_maintenance = True
    machines["M03"].is_active = False
    db_session.commit()
    for m, code in ((m2, "MACHINE_IN_MAINTENANCE"), (machines["M03"], "MACHINE_INACTIVE")):
        body = {"assignments": [{"machine_id": m.id, "planned_liters": "100"}]}
        resp = client.put(url, json=body, headers=jefe)
        assert resp.status_code == 422 and resp.json()["error"]["code"] == code

    # Without expiry the split is saved but the order stays Creada (BR-20).
    data = _assign(client, jefe, oid, [(m1, "100")])
    assert data["status"] == "created"
    assert data["missing_for_assign"] == ["expiry"]
    # Cannot start without being assigned.
    resp = client.post(f"{API}/assignments/{data['assignments'][0]['id']}/start", headers=jefe)
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "ORDER_NOT_ASSIGNED"

    # Empty list removes everything; clearing a Trabajo expiry returns to Creada.
    _expiry(client, jefe, oid, "2029-01-01")
    assert _order(client, oid)["status"] == "assigned"
    data = _expiry(client, jefe, oid, None)
    assert data["status"] == "created"
    _expiry(client, jefe, oid, "2029-01-01")
    data = _assign(client, jefe, oid, [])
    assert data["status"] == "created" and data["assignments"] == []


def test_replacing_split_keeps_queue_position_of_kept_machines(
    client, db_session, cliente, base_calcio, nh_calcio, machines, calcio_stock, jefe
):
    first = _ready_order(client, db_session, jefe, cliente, base_calcio, nh_calcio, machines,
                         split=[(machines["M01"], "100")])
    second = _ready_order(client, db_session, jefe, cliente, base_calcio, nh_calcio, machines,
                          split=[(machines["M01"], "60"), (machines["M02"], "40")])
    pos = _by_machine(second)["M01"]["queue_position"]
    data = _assign(client, jefe, second["id"], [(machines["M01"], "50"), (machines["M03"], "50")])
    assert _by_machine(data)["M01"]["queue_position"] == pos
    assert set(_by_machine(data)) == {"M01", "M03"}
    assert _by_machine(_order(client, first["id"]))["M01"]["queue_position"] < pos


# Expiry locks (BR-20) -----------------------------------------------------------------------


def test_retrabajo_expiry_locked(client, db_session, cliente, base_calcio, nh_calcio, machines,
                                 calcio_stock, jefe):
    # A closed order to rework.
    done = _ready_order(client, db_session, jefe, cliente, base_calcio, nh_calcio, machines,
                        split=[(machines["M01"], "100")])
    aid = done["assignments"][0]["id"]
    _act(client, jefe, aid, "start")
    _act(client, jefe, aid, "complete", actual_liters="100")

    prev = _create(client, jefe, None, [(base_calcio.id, "10")], nh_calcio.id,
                   order_type="retrabajo", rework_kind="previous_order",
                   related_order_id=done["id"])
    assert prev["expiry_date"] == "2029-03-01" and prev["expiry_locked"] is True
    assert prev["can_set_expiry"] is False
    resp = client.put(f"{API}/orders/{prev['id']}/expiry", json={"expiry_date": "2030-01-01"},
                      headers=jefe)
    assert resp.status_code == 409 and resp.json()["error"]["code"] == "EXPIRY_LOCKED"

    own = _create(client, jefe, None, [(base_calcio.id, "10")], nh_calcio.id,
                  order_type="retrabajo", rework_kind="own_stock")
    assert own["expiry_locked"] is False
    resp = client.put(f"{API}/orders/{own['id']}/expiry", json={"expiry_date": None},
                      headers=jefe)
    assert resp.status_code == 422
    data = _expiry(client, jefe, own["id"], "2028-06-01")
    assert data["expiry_locked"] is True
    resp = client.put(f"{API}/orders/{own['id']}/expiry", json={"expiry_date": "2028-07-01"},
                      headers=jefe)
    assert resp.status_code == 409


def test_trabajo_expiry_editable_until_production_starts(
    client, db_session, cliente, base_calcio, nh_calcio, machines, calcio_stock, jefe
):
    order = _ready_order(client, db_session, jefe, cliente, base_calcio, nh_calcio, machines)
    data = _expiry(client, jefe, order["id"], "2030-05-01")
    assert data["expiry_date"] == "2030-05-01" and data["status"] == "assigned"
    _act(client, jefe, _by_machine(order)["M01"]["id"], "start")
    resp = client.put(f"{API}/orders/{order['id']}/expiry", json={"expiry_date": "2031-01-01"},
                      headers=jefe)
    assert resp.status_code == 409 and resp.json()["error"]["code"] == "EXPIRY_LOCKED"


# BR-16: editing an assigned order --------------------------------------------------------------


def test_editing_products_of_assigned_order_deletes_assignments(
    client, db_session, cliente, base_calcio, nh_calcio, machines, calcio_stock, jefe
):
    order = _ready_order(client, db_session, jefe, cliente, base_calcio, nh_calcio, machines)
    oid = order["id"]
    assert order["can_edit"] is True

    # Non-product fields keep the assignments.
    resp = client.patch(f"{API}/orders/{oid}", json={"labels_planned": 5}, headers=jefe)
    assert resp.status_code == 200 and resp.json()["status"] == "assigned"
    assert len(resp.json()["assignments"]) == 2

    resp = client.patch(
        f"{API}/orders/{oid}",
        json={"base_products": [{"product_id": base_calcio.id, "liters": "120"}],
              "finished_liters": "120"},
        headers=jefe,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["status"] == "created"
    assert data["assignments"] == []
    assert data["missing_for_assign"] == ["machines"]
    db_session.expire_all()
    assert db_session.query(Assignment).filter(Assignment.order_id == oid).count() == 0
    entry = (
        db_session.query(AuditLog)
        .filter(AuditLog.entity == "work_order", AuditLog.entity_id == oid,
                AuditLog.action == "update")
        .order_by(AuditLog.id.desc()).first()
    )
    assert len(entry.after["removed_assignments"]) == 2
    assert client.get(f"{API}/production/to-assign").json()[0]["id"] == oid


def test_order_not_editable_once_started(client, db_session, cliente, base_calcio, nh_calcio,
                                         machines, calcio_stock, jefe):
    order = _ready_order(client, db_session, jefe, cliente, base_calcio, nh_calcio, machines)
    _act(client, jefe, _by_machine(order)["M01"]["id"], "start")
    resp = client.patch(f"{API}/orders/{order['id']}", json={"labels_planned": 5}, headers=jefe)
    assert resp.status_code == 409 and resp.json()["error"]["code"] == "ORDER_NOT_EDITABLE"
    resp = client.put(f"{API}/orders/{order['id']}/assignments", json={"assignments": []},
                      headers=jefe)
    assert resp.status_code == 409 and resp.json()["error"]["code"] == "ASSIGNMENTS_LOCKED"


# BR-17: cancel ------------------------------------------------------------------------------------


def test_cancel_assigned_order_cancels_assignments_and_refused_once_started(
    client, db_session, cliente, base_calcio, nh_calcio, machines, calcio_stock, jefe
):
    order = _ready_order(client, db_session, jefe, cliente, base_calcio, nh_calcio, machines)
    resp = client.post(f"{API}/orders/{order['id']}/cancel", json={"reason": "cliente"},
                       headers=jefe)
    assert resp.status_code == 200
    assert {a["status"] for a in resp.json()["assignments"]} == {"cancelled"}
    board = {m["code"]: m for m in client.get(f"{API}/machines/board").json()}
    assert board["M01"]["queue_length"] == 0

    started = _ready_order(client, db_session, jefe, cliente, base_calcio, nh_calcio, machines)
    _act(client, jefe, _by_machine(started)["M01"]["id"], "start")
    resp = client.post(f"{API}/orders/{started['id']}/cancel", json={"reason": "x"},
                       headers=jefe)
    assert resp.status_code == 409 and resp.json()["error"]["code"] == "INVALID_TRANSITION"


# BR-14: one running/paused per machine, queue order --------------------------------------------


def test_one_active_assignment_per_machine_and_queue_order(
    client, db_session, cliente, base_calcio, nh_calcio, machines, calcio_stock, jefe
):
    m1 = machines["M01"]
    a = _ready_order(client, db_session, jefe, cliente, base_calcio, nh_calcio, machines,
                     split=[(m1, "100")])
    b = _ready_order(client, db_session, jefe, cliente, base_calcio, nh_calcio, machines,
                     split=[(m1, "100")])
    a_id, b_id = a["assignments"][0]["id"], b["assignments"][0]["id"]

    # Queue order: B cannot jump ahead of A.
    resp = client.post(f"{API}/assignments/{b_id}/start", headers=jefe)
    assert resp.status_code == 409 and resp.json()["error"]["code"] == "MACHINE_NOT_READY"
    assert _order(client, b["id"])["assignments"][0]["can_start"] is False

    # Reorder: B first.
    resp = client.patch(f"{API}/assignments/{b_id}/queue-position", json={"queue_position": 1},
                        headers=jefe)
    assert resp.status_code == 200 and resp.json()["queue_position"] == 1
    queue = client.get(f"{API}/machines/{m1.id}/queue").json()
    assert [p["id"] for p in queue["pending"]] == [b_id, a_id]
    _act(client, jefe, b_id, "start")

    # Machine busy: A cannot start, even while B is paused.
    assert client.post(f"{API}/assignments/{a_id}/start", headers=jefe).status_code == 409
    _act(client, jefe, b_id, "pause")
    resp = client.post(f"{API}/assignments/{a_id}/start", headers=jefe)
    assert resp.status_code == 409
    assert "ocupada" in resp.json()["error"]["message"]
    # Running assignments cannot be reordered.
    resp = client.patch(f"{API}/assignments/{b_id}/queue-position", json={"queue_position": 2},
                        headers=jefe)
    assert resp.status_code == 409

    _act(client, jefe, b_id, "resume")
    _act(client, jefe, b_id, "complete", actual_liters="100")
    data = _act(client, jefe, a_id, "start")
    assert data["status"] == "running"


def test_invalid_assignment_transitions(client, db_session, cliente, base_calcio, nh_calcio,
                                        machines, calcio_stock, jefe):
    order = _ready_order(client, db_session, jefe, cliente, base_calcio, nh_calcio, machines,
                         split=[(machines["M01"], "100")])
    aid = order["assignments"][0]["id"]
    for action, body in (("pause", {}), ("resume", {}), ("complete", {"actual_liters": "1"})):
        resp = client.post(f"{API}/assignments/{aid}/{action}", json=body or None, headers=jefe)
        assert resp.status_code == 409 and resp.json()["error"]["code"] == "INVALID_TRANSITION"
    _act(client, jefe, aid, "start")
    assert client.post(f"{API}/assignments/{aid}/start", headers=jefe).status_code == 409
    assert client.post(f"{API}/assignments/{aid}/resume", headers=jefe).status_code == 409
    resp = client.post(f"{API}/assignments/{aid}/complete", json={"actual_liters": "-1"},
                       headers=jefe)
    assert resp.status_code == 422
    resp = client.post(f"{API}/assignments/{aid}/complete", json={"actual_liters": "1.234"},
                       headers=jefe)
    assert resp.status_code == 422


def test_start_refused_on_machine_in_maintenance(client, db_session, cliente, base_calcio,
                                                 nh_calcio, machines, calcio_stock, jefe):
    order = _ready_order(client, db_session, jefe, cliente, base_calcio, nh_calcio, machines,
                         split=[(machines["M01"], "100")])
    machines["M01"].in_maintenance = True
    db_session.commit()
    aid = order["assignments"][0]["id"]
    resp = client.post(f"{API}/assignments/{aid}/start", headers=jefe)
    assert resp.status_code == 409
    assert "mantenimiento" in resp.json()["error"]["message"]
    board = {m["code"]: m for m in client.get(f"{API}/machines/board").json()}
    assert board["M01"]["state"] == "maintenance"


# BR-23: pause / resume and derived order status ----------------------------------------------


def test_derived_order_status(client, db_session, cliente, base_calcio, nh_calcio, machines,
                              calcio_stock, jefe):
    order = _ready_order(client, db_session, jefe, cliente, base_calcio, nh_calcio, machines)
    oid = order["id"]
    m1, m4 = _by_machine(order)["M01"]["id"], _by_machine(order)["M04"]["id"]

    _act(client, jefe, m1, "start")
    assert _order(client, oid)["status"] == "in_progress"
    _act(client, jefe, m1, "pause")
    assert _order(client, oid)["status"] == "paused"  # M04 not started
    _act(client, jefe, m4, "start")
    _act(client, jefe, m1, "resume")
    _act(client, jefe, m1, "pause")
    assert _order(client, oid)["status"] == "in_progress"  # one running + one paused
    _act(client, jefe, m4, "pause")
    assert _order(client, oid)["status"] == "paused"  # both paused
    _act(client, jefe, m4, "complete", actual_liters="30")
    assert _order(client, oid)["status"] == "paused"  # one completed + one paused
    # Pausing never releases reservations or stock (BR-23).
    assert _active_reservations(db_session, oid)  # still holding the M01 share
    _act(client, jefe, m1, "complete", actual_liters="70")
    assert _order(client, oid)["status"] == "completed"


# Scenarios 2, 3, 4, 6 / BR-8 / BR-10 / BR-11 / BR-12 -----------------------------------------


def test_scenarios_2_to_4_full_process_without_plcs(
    client, db_session, site, cliente, base_calcio, nh_calcio, envase, machines, calcio_stock,
    jefe,
):
    _stock(db_session, site.id, ItemRef("packaging", envase.id), "100")
    order = _create(client, jefe, cliente.id, [(base_calcio.id, "100")], nh_calcio.id,
                    packaging=[{"packaging_item_id": envase.id, "planned_qty": 5}],
                    labels_planned=5)
    oid = order["id"]
    _expiry(client, jefe, oid, "2029-03-01")
    order = _assign(client, jefe, oid, [(machines["M01"], "70"), (machines["M04"], "30")])
    m1, m4 = _by_machine(order)["M01"]["id"], _by_machine(order)["M04"]["id"]

    # Scenario 2.
    _act(client, jefe, m1, "start")
    _act(client, jefe, m1, "pause")
    assert _order(client, oid)["status"] == "paused"
    _act(client, jefe, m1, "resume")
    _act(client, jefe, m4, "start")
    assert _order(client, oid)["status"] == "in_progress"

    # Scenario 3.
    _act(client, jefe, m1, "complete", actual_liters="70")
    _act(client, jefe, m4, "complete", actual_liters="29")
    data = _order(client, oid)
    assert data["status"] == "completed"
    assert data["difference"] == {
        "ordered_liters": "100.00", "actual_liters": "99.00", "difference": "-1.00",
        "within_range": False,
    }
    assert _on_hand(db_session, site.id, ItemRef("product", base_calcio.id)) == Decimal("1401")
    assert _on_hand(db_session, site.id, ItemRef("product", nh_calcio.id)) == Decimal("99")
    assert _on_hand(db_session, site.id, ItemRef("packaging", envase.id)) == Decimal("95")
    assert _active_reservations(db_session, oid) == {}  # 1 L + packaging released
    db_session.expire_all()
    statuses = {
        (r.status, str(r.quantity))
        for r in db_session.query(Reservation).filter(Reservation.order_id == oid,
                                                      Reservation.product_id.is_not(None))
    }
    assert statuses == {("consumed", "70.00"), ("consumed", "29.00"), ("released", "1.00")}
    to_close = client.get(f"{API}/production/to-close").json()
    assert [r["id"] for r in to_close] == [oid]
    assert to_close[0]["difference"]["difference"] == "-1.00"
    assert data["close_missing"] == ["checklist", "new_lot", "materials", "labels"]
    movements = db_session.query(StockMovement).filter(StockMovement.order_id == oid).all()
    assert {(m.type, str(m.quantity)) for m in movements} == {
        ("production", "70.00"), ("production", "29.00"),
        ("consumption", "-70.00"), ("consumption", "-29.00"), ("consumption", "-5.00"),
    }

    # Scenario 4: traceability, then close; an admin can still comment.
    resp = client.patch(f"{API}/orders/{oid}/checklist", json={"items": [
        {"item": i, "checked": True}
        for i in ("lote_etiqueta", "niveles_producto", "cantidades", "embalaje")
    ]}, headers=jefe)
    assert resp.status_code == 200
    resp = client.patch(f"{API}/orders/{oid}/traceability", json={"new_lot": "L-0326"},
                        headers=jefe)
    assert resp.json()["new_lot"] == "L-0326"
    resp = client.patch(f"{API}/orders/{oid}/materials", json={
        "packaging": [{"packaging_item_id": envase.id, "actual_qty": 6}], "labels_actual": 6,
    }, headers=jefe)
    assert resp.status_code == 200
    # Correction after completion writes only the difference.
    assert _on_hand(db_session, site.id, ItemRef("packaging", envase.id)) == Decimal("94")
    assert resp.json()["close_missing"] == []

    resp = client.post(f"{API}/orders/{oid}/close", json={"note": "Faltante aceptado"},
                       headers=jefe)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["status"] == "closed"
    assert data["closed_by_name"] == "Jane Doe" and data["close_note"] == "Faltante aceptado"
    assert data["can_edit_traceability"] is False

    admin = login_as(client, db_session, "admin")
    resp = client.post(f"{API}/orders/{oid}/comments", json={"text": "Entregado"}, headers=admin)
    assert resp.status_code == 201
    for path, body in (
        ("checklist", {"items": [{"item": "embalaje", "checked": False}]}),
        ("traceability", {"new_lot": "X"}),
        ("materials", {"labels_actual": 1}),
    ):
        resp = client.patch(f"{API}/orders/{oid}/{path}", json=body, headers=admin)
        assert resp.status_code == 409 and resp.json()["error"]["code"] == "ORDER_READ_ONLY"
    jefe = login_as(client, db_session, "production_manager")
    resp = client.post(f"{API}/orders/{oid}/close", json={}, headers=jefe)
    assert resp.status_code == 409

    # Scenario 6: history shows every event with user and source manual.
    history = client.get(f"{API}/orders/{oid}/history").json()
    actions = [h["action"] for h in reversed(history)]
    for action in ("create", "expiry", "assign", "start", "pause", "resume", "complete",
                   "checklist", "traceability", "materials", "close", "comment"):
        assert action in actions, action
    for h in history:
        if h["action"] in ("start", "pause", "resume", "complete"):
            assert h["after"]["source"] == "manual"
            assert h["user_name"] == "Jane Doe"
    events = db_session.query(AssignmentEvent).filter(AssignmentEvent.source == "manual").all()
    assert {e.event for e in events} >= {"assign", "start", "pause", "resume", "complete"}
    assert all(e.user_id is not None and e.machine_id is None for e in events)

    # Printing shows who assigned and who closed.
    pdata = client.get(f"{API}/orders/{oid}/print-data").json()
    assert pdata["assigned"]["name"] == "Jane Doe"
    assert pdata["closed"]["name"] == "Jane Doe"
    assert len(pdata["order"]["assignments"]) == 2


def test_scenario5_mixed_order_proportional_consumption(
    client, db_session, site, cliente, base_calcio, nb_neem, nh_calcio, machines, jefe
):
    _stock(db_session, site.id, ItemRef("product", nb_neem.id), "600")
    _stock(db_session, site.id, ItemRef("product", base_calcio.id), "400")
    order = _create(client, jefe, cliente.id, [(nb_neem.id, "600"), (base_calcio.id, "400")],
                    nh_calcio.id, razon_social_id=_rs(db_session, "NB").id)
    assert order["finished_liters"] == "1000.00"
    _expiry(client, jefe, order["id"], "2029-03-01")
    order = _assign(client, jefe, order["id"], [(machines["M02"], "1000")])
    aid = order["assignments"][0]["id"]
    _act(client, jefe, aid, "start")
    _act(client, jefe, aid, "complete", actual_liters="990")
    assert _on_hand(db_session, site.id, ItemRef("product", nb_neem.id)) == Decimal("6")
    assert _on_hand(db_session, site.id, ItemRef("product", base_calcio.id)) == Decimal("4")
    assert _on_hand(db_session, site.id, ItemRef("product", nh_calcio.id)) == Decimal("990")
    data = _order(client, order["id"])
    assert data["difference"]["difference"] == "-10.00"


def test_rounding_does_not_lose_liters_across_assignments(
    client, db_session, site, cliente, base_calcio, nb_neem, nh_calcio, machines, jefe
):
    """Three base products of 1/3 each, three machines: per-assignment shares
    are rounded, but the totals consumed equal the exact cumulative share."""
    third = _product(db_session, "TERCERO", "TERCERO", "1000", "ANB")
    for p in (nb_neem, base_calcio, third):
        _stock(db_session, site.id, ItemRef("product", p.id), "100")
    order = _create(client, jefe, cliente.id,
                    [(nb_neem.id, "33.33"), (base_calcio.id, "33.33"), (third.id, "33.34")],
                    nh_calcio.id, razon_social_id=_rs(db_session, "ANB").id)
    _expiry(client, jefe, order["id"], "2029-03-01")
    order = _assign(client, jefe, order["id"], [
        (machines["M01"], "33.33"), (machines["M02"], "33.33"), (machines["M03"], "33.34"),
    ])
    for code, liters in (("M01", "33.33"), ("M02", "33.33"), ("M03", "33.34")):
        aid = _by_machine(order)[code]["id"]
        _act(client, jefe, aid, "start")
        _act(client, jefe, aid, "complete", actual_liters=liters)
    db_session.expire_all()
    consumed = {
        p.code: -sum(
            Decimal(m.quantity)
            for m in db_session.query(StockMovement).filter(
                StockMovement.order_id == order["id"], StockMovement.product_id == p.id,
                StockMovement.type == "consumption",
            )
        )
        for p in (nb_neem, base_calcio, third)
    }
    assert consumed == {"GRN100C1XL20F004": Decimal("33.33"), "QVR200C1XL09M01": Decimal("33.33"),
                        "TERCERO": Decimal("33.34")}
    assert _active_reservations(db_session, order["id"]) == {}


def test_negative_stock_allowed_and_alerted(client, db_session, site, cliente, base_calcio,
                                            nh_calcio, machines, jefe):
    _stock(db_session, site.id, ItemRef("product", base_calcio.id), "100")
    order = _ready_order(client, db_session, jefe, cliente, base_calcio, nh_calcio, machines,
                         split=[(machines["M01"], "100")])
    # Stock is adjusted down after the order was created (e.g. a recount).
    stock_service.apply_movement(
        db_session, site_id=site.id, item=ItemRef("product", base_calcio.id),
        movement_type="adjustment", quantity=Decimal("-50"), user=None,
    )
    db_session.commit()
    aid = order["assignments"][0]["id"]
    _act(client, jefe, aid, "start")
    _act(client, jefe, aid, "complete", actual_liters="110")  # excedente
    assert _on_hand(db_session, site.id, ItemRef("product", base_calcio.id)) == Decimal("-60")
    alerts = client.get(f"{API}/inventory/alerts").json()
    assert any(a["item_id"] == base_calcio.id and a["kind"] == "negative_stock"
               for a in alerts["negative_stock"]), alerts


# BR-12 tolerance ---------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "liters_tol,percent_tol,actual,within",
    [
        (0, 0, "100", True),
        (0, 0, "99", False),
        (1, 0, "99", True),
        (1, 0, "101.5", False),
        (0, 2, "98", True),
        (0, 2, "97.99", False),
        (0.5, 1, "101", True),  # percent passes even though liters fail
    ],
)
def test_difference_tolerance(client, db_session, cliente, base_calcio, nh_calcio, machines,
                              calcio_stock, jefe, liters_tol, percent_tol, actual, within):
    master = login_as(client, db_session, "master_admin")
    for key, value in (("difference_tolerance_liters", liters_tol),
                       ("difference_tolerance_percent", percent_tol)):
        resp = client.patch(f"{API}/settings/{key}", json={"value": value}, headers=master)
        assert resp.status_code == 200, resp.text
    jefe = login_as(client, db_session, "production_manager")
    order = _ready_order(client, db_session, jefe, cliente, base_calcio, nh_calcio, machines,
                         split=[(machines["M01"], "100")])
    aid = order["assignments"][0]["id"]
    _act(client, jefe, aid, "start")
    _act(client, jefe, aid, "complete", actual_liters=actual)
    assert _order(client, order["id"])["difference"]["within_range"] is within
    # Closing is allowed regardless (BR-11).
    assert client.post(f"{API}/orders/{order['id']}/close", json={},
                       headers=jefe).status_code == 200


# BR-11 / BR-24 permissions --------------------------------------------------------------------


def test_only_orders_close_can_close_and_admin_fills_traceability(
    client, db_session, cliente, base_calcio, nh_calcio, envase, machines, calcio_stock, jefe
):
    order = _create(client, jefe, cliente.id, [(base_calcio.id, "100")], nh_calcio.id,
                    packaging=[{"packaging_item_id": envase.id, "planned_qty": 2}])
    oid = order["id"]
    admin = login_as(client, db_session, "admin")
    # Admin fills traceability before production too (who and when recorded).
    resp = client.patch(f"{API}/orders/{oid}/checklist",
                        json={"items": [{"item": "embalaje", "checked": True}]}, headers=admin)
    assert resp.status_code == 200
    item = next(c for c in resp.json()["checklist"] if c["item"] == "embalaje")
    assert item["checked"] is True and item["checked_by_name"] == "Jane Doe"
    assert item["checked_at"] is not None
    resp = client.patch(f"{API}/orders/{oid}/traceability",
                        json={"new_lot": "L1", "previous_lot": "L0"}, headers=admin)
    data = resp.json()
    assert data["new_lot"] == "L1" and data["previous_lot"] == "L0"
    assert data["new_lot_by_name"] == "Jane Doe" and data["new_lot_at"]
    resp = client.patch(f"{API}/orders/{oid}/materials", json={
        "packaging": [{"packaging_item_id": envase.id, "actual_qty": 3}], "labels_actual": 4,
    }, headers=admin)
    data = resp.json()
    assert data["packaging"][0]["actual_qty"] == 3
    assert data["packaging"][0]["actual_by_name"] == "Jane Doe"
    assert data["labels_actual"] == 4 and data["labels_actual_by_name"] == "Jane Doe"
    # Not part of the order -> refused.
    other = db_session.query(PackagingItem).filter(PackagingItem.code == "CAJ01AZ002").one()
    resp = client.patch(f"{API}/orders/{oid}/materials", json={
        "packaging": [{"packaging_item_id": other.id, "actual_qty": 1}]}, headers=admin)
    assert resp.status_code == 422

    # Admin cannot assign, set expiry, control production or close.
    assert client.put(f"{API}/orders/{oid}/expiry", json={"expiry_date": "2029-01-01"},
                      headers=admin).status_code == 403
    assert client.put(f"{API}/orders/{oid}/assignments", json={"assignments": []},
                      headers=admin).status_code == 403
    assert client.get(f"{API}/production/to-assign").status_code == 403

    jefe = login_as(client, db_session, "production_manager")
    _expiry(client, jefe, oid, "2029-01-01")
    order = _assign(client, jefe, oid, [(machines["M01"], "100")])
    aid = order["assignments"][0]["id"]
    admin = login_as(client, db_session, "admin")
    assert client.post(f"{API}/assignments/{aid}/start", headers=admin).status_code == 403
    jefe = login_as(client, db_session, "production_manager")
    _act(client, jefe, aid, "start")
    # Packaging consumed at completion uses the actual quantity entered (3).
    _act(client, jefe, aid, "complete", actual_liters="100")
    admin = login_as(client, db_session, "admin")
    assert client.post(f"{API}/orders/{oid}/close", json={}, headers=admin).status_code == 403
    # Board is visible to the admin.
    assert client.get(f"{API}/machines/board").status_code == 200
    db_session.expire_all()
    pkg = db_session.query(StockMovement).filter(
        StockMovement.order_id == oid, StockMovement.packaging_item_id == envase.id
    ).one()
    assert pkg.quantity == Decimal("-3")


ENDPOINT_ROLES = [
    ("get", "/production/to-assign", {"master_admin", "production_manager"}),
    ("get", "/production/in-production", {"master_admin", "production_manager"}),
    ("get", "/production/to-close", {"master_admin", "production_manager"}),
    ("get", "/machines/board", {"master_admin", "admin", "production_manager"}),
]


@pytest.mark.parametrize("method,path,allowed", ENDPOINT_ROLES)
@pytest.mark.parametrize("role", ["master_admin", "admin", "production_manager"])
def test_production_read_permissions(client, db_session, base_catalogs, method, path, allowed,
                                     role):
    login_as(client, db_session, role)
    resp = getattr(client, method)(f"{API}{path}")
    assert resp.status_code == (200 if role in allowed else 403)


# Machine board -------------------------------------------------------------------------------


def test_machine_board_states(client, db_session, cliente, base_calcio, nh_calcio, machines,
                              calcio_stock, jefe):
    order = _ready_order(client, db_session, jefe, cliente, base_calcio, nh_calcio, machines)
    _ready_order(client, db_session, jefe, cliente, base_calcio, nh_calcio, machines,
                 split=[(machines["M01"], "100")])
    m1, m4 = _by_machine(order)["M01"]["id"], _by_machine(order)["M04"]["id"]
    _act(client, jefe, m1, "start")
    _act(client, jefe, m4, "start")
    _act(client, jefe, m4, "pause")
    machines["M06"].in_maintenance = True
    db_session.commit()
    board = {m["code"]: m for m in client.get(f"{API}/machines/board").json()}
    assert board["M01"]["state"] == "busy"
    assert board["M01"]["current"]["operation_number"] == order["operation_number"]
    assert board["M01"]["current"]["can_pause"] is True
    assert board["M01"]["queue_length"] == 1
    assert board["M04"]["state"] == "paused" and board["M04"]["current"]["can_resume"] is True
    assert board["M02"]["state"] == "free" and board["M02"]["current"] is None
    assert board["M06"]["state"] == "maintenance"
    # The Production manager cannot toggle maintenance (catalogs.manage).
    resp = client.patch(f"{API}/machines/{machines['M02'].id}", json={"in_maintenance": True},
                        headers=jefe)
    assert resp.status_code == 403
    admin = login_as(client, db_session, "admin")
    resp = client.patch(f"{API}/machines/{machines['M02'].id}", json={"in_maintenance": True},
                        headers=admin)
    assert resp.status_code == 200


def test_plc_actor_uses_same_rules(db_session, client, cliente, base_calcio, nh_calcio,
                                   machines, calcio_stock, jefe):
    """Phase 4 hook: the same service functions with a machine as the actor."""
    from app.services import assignment_service
    from app.services.assignment_service import Actor

    order = _ready_order(client, db_session, jefe, cliente, base_calcio, nh_calcio, machines)
    m1 = _by_machine(order)["M01"]["id"]
    db_session.expire_all()
    with pytest.raises(Exception) as exc:
        assignment_service.start(db_session, m1, Actor.plc(machines["M04"]))
    assert getattr(exc.value, "code", None) == "WRONG_MACHINE"
    db_session.rollback()
    assignment_service.start(db_session, m1, Actor.plc(machines["M01"]))
    db_session.expire_all()
    row = db_session.get(Assignment, m1)
    assert row.status == "running" and row.last_source == "plc"
    event = db_session.query(AssignmentEvent).filter(
        AssignmentEvent.assignment_id == m1, AssignmentEvent.event == "start").one()
    assert event.source == "plc" and event.machine_id == machines["M01"].id
    assert event.user_id is None
    assert db_session.get(WorkOrder, order["id"]).status == "in_progress"
