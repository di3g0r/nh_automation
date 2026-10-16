"""Phase 4: PLC event processor (BR-13), PLC credentials permission, machine
board PLC data. Runs on SQLite: events are inserted with `machine_id` set
directly (on PostgreSQL the insert trigger sets it from the PLC login; that
part is covered by tests/test_plc_postgres.py)."""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy.orm import sessionmaker

from app.models.assignments import Assignment, AssignmentEvent
from app.models.audit_log import AuditLog
from app.models.plc import PlcEvent
from app.models.stock import StockMovement
from app.services import plc_event_service
from app.services.plc_credentials_service import username_for
from app.services.stock_service import ItemRef
from tests.conftest import login_as
from tests.test_production import (  # noqa: F401 - fixtures (see pyproject)
    API,
    _act,
    _assign,
    _by_machine,
    _create,
    _expiry,
    _on_hand,
    _order,
    _ready_order,
    base_calcio,
    calcio_stock,
    cliente,
    jefe,
    machines,
    nh_calcio,
    site,
)


@pytest.fixture()
def factory(engine):
    return sessionmaker(bind=engine, autoflush=False)


def _insert(db_session, machine, assignment_id, event, liters=None, seq=None, **extra) -> int:
    row = PlcEvent(
        machine_id=machine.id, assignment_id=assignment_id, event=event,
        liters=Decimal(liters) if liters is not None else None, seq=seq, **extra,
    )
    db_session.add(row)
    db_session.commit()
    return row.id


def _event(db_session, event_id) -> PlcEvent:
    db_session.expire_all()
    return db_session.get(PlcEvent, event_id)


def _process(factory) -> int:
    return plc_event_service.process_pending(factory)


@pytest.fixture()
def order(client, db_session, cliente, base_calcio, nh_calcio, machines, calcio_stock, jefe):
    """100 L split 70 L on M01 and 30 L on M04."""
    return _ready_order(client, db_session, jefe, cliente, base_calcio, nh_calcio, machines)


def test_happy_path_start_progress_complete(client, db_session, factory, machines, order):
    a1 = _by_machine(order)["M01"]["id"]
    m1 = machines["M01"]
    ids = [
        _insert(db_session, m1, a1, "start", seq=1),
        _insert(db_session, m1, a1, "progress", "20", seq=2),
        _insert(db_session, m1, a1, "progress", "45.5", seq=3),
    ]
    assert _process(factory) == 3
    assert [_event(db_session, i).result for i in ids] == ["applied"] * 3
    data = _order(client, order["id"])
    row = _by_machine(data)["M01"]
    assert data["status"] == "in_progress"
    assert row["status"] == "running" and row["last_source"] == "plc"
    assert Decimal(row["actual_liters"]) == Decimal("45.50")

    done = _insert(db_session, m1, a1, "complete", "70", seq=4)
    _process(factory)
    assert _event(db_session, done).result == "applied"
    row = _by_machine(_order(client, order["id"]))["M01"]
    assert row["status"] == "completed" and Decimal(row["actual_liters"]) == Decimal("70.00")
    # History records the PLC as the source, without a user.
    history = client.get(f"{API}/orders/{order['id']}/history").json()
    complete = next(h for h in history if h["action"] == "complete")
    assert complete["user_id"] is None
    assert complete["after"]["source"] == "plc" and complete["after"]["plc_machine"] == "M01"
    # Nothing left to process.
    assert _process(factory) == 0


def test_duplicate_seq_is_not_applied(client, db_session, factory, machines, order):
    a1 = _by_machine(order)["M01"]["id"]
    m1, m4 = machines["M01"], machines["M04"]
    _insert(db_session, m1, a1, "start", seq=10)
    _insert(db_session, m1, a1, "progress", "30", seq=11)
    dup = _insert(db_session, m1, a1, "progress", "30", seq=11)
    _process(factory)
    assert _event(db_session, dup).result == "duplicate"
    # Same seq on another machine is not a duplicate (seq is per machine).
    a4 = _by_machine(order)["M04"]["id"]
    other = _insert(db_session, m4, a4, "start", seq=10)
    # A repeated complete does not move stock twice.
    c1 = _insert(db_session, m1, a1, "complete", "70", seq=12)
    c2 = _insert(db_session, m1, a1, "complete", "70", seq=12)
    _process(factory)
    assert _event(db_session, other).result == "applied"
    assert (_event(db_session, c1).result, _event(db_session, c2).result) == (
        "applied", "duplicate"
    )
    db_session.expire_all()
    produced = db_session.query(StockMovement).filter(
        StockMovement.order_id == order["id"], StockMovement.type == "production"
    ).all()
    assert [Decimal(m.quantity) for m in produced] == [Decimal("70.00")]


def test_events_without_seq_are_never_duplicates(client, db_session, factory, machines, order):
    a1 = _by_machine(order)["M01"]["id"]
    m1 = machines["M01"]
    _insert(db_session, m1, a1, "start")
    p1 = _insert(db_session, m1, a1, "progress", "10")
    p2 = _insert(db_session, m1, a1, "progress", "10")
    _process(factory)
    assert {_event(db_session, p1).result, _event(db_session, p2).result} == {"applied"}


def test_out_of_order_progress_never_decreases(client, db_session, factory, machines, order):
    a1 = _by_machine(order)["M01"]["id"]
    m1 = machines["M01"]
    _insert(db_session, m1, a1, "start", seq=1)
    _insert(db_session, m1, a1, "progress", "50", seq=3)
    late = _insert(db_session, m1, a1, "progress", "40", seq=2)
    _process(factory)
    assert _event(db_session, late).result == "applied"  # valid, just no change
    db_session.expire_all()
    assert Decimal(db_session.get(Assignment, a1).actual_liters) == Decimal("50.00")
    # Progress writes no assignment event or audit entry (kept in plc_events).
    assert db_session.query(AssignmentEvent).filter(
        AssignmentEvent.assignment_id == a1, AssignmentEvent.event == "progress"
    ).count() == 0


def test_start_on_non_first_assignment_rejected(
    client, db_session, factory, cliente, base_calcio, nh_calcio, machines, calcio_stock, jefe
):
    m1 = machines["M01"]
    first = _ready_order(client, db_session, jefe, cliente, base_calcio, nh_calcio, machines,
                         split=[(m1, "100")])
    second = _ready_order(client, db_session, jefe, cliente, base_calcio, nh_calcio, machines,
                          split=[(m1, "100")])
    a_first = first["assignments"][0]["id"]
    a_second = second["assignments"][0]["id"]
    bad = _insert(db_session, m1, a_second, "start", seq=1)
    _process(factory)
    ev = _event(db_session, bad)
    assert ev.result == "rejected" and ev.reject_reason.startswith("NOT_FIRST_IN_QUEUE")
    # While the first one runs, starting the second is an invalid transition.
    _insert(db_session, m1, a_first, "start", seq=2)
    busy = _insert(db_session, m1, a_second, "start", seq=3)
    _process(factory)
    ev = _event(db_session, busy)
    assert ev.result == "rejected" and ev.reject_reason.startswith("INVALID_TRANSITION")
    assert _order(client, second["id"])["status"] == "assigned"


def test_event_for_another_machines_assignment_rejected(
    client, db_session, factory, machines, order
):
    a1 = _by_machine(order)["M01"]["id"]
    wrong = _insert(db_session, machines["M04"], a1, "start", seq=1)
    unknown = _insert(db_session, machines["M01"], 999_999, "start", seq=2)
    _process(factory)
    for event_id in (wrong, unknown):
        ev = _event(db_session, event_id)
        assert ev.result == "rejected" and ev.reject_reason.startswith("NOT_ON_MACHINE")
    assert _by_machine(_order(client, order["id"]))["M01"]["status"] == "pending"


@pytest.mark.parametrize(
    "event,liters,assignment,reason",
    [
        ("start", None, None, "BAD_PAYLOAD"),
        ("complete", None, "a1", "BAD_PAYLOAD"),
        ("progress", None, "a1", "BAD_PAYLOAD"),
        ("pause", None, "a1", "INVALID_TRANSITION"),  # pending, not running
        ("resume", None, "a1", "INVALID_TRANSITION"),
        ("complete", "70", "a1", "INVALID_TRANSITION"),  # never started
    ],
)
def test_invalid_events_rejected_with_reason(
    client, db_session, factory, machines, order, event, liters, assignment, reason
):
    a1 = _by_machine(order)["M01"]["id"]
    ev_id = _insert(db_session, machines["M01"], a1 if assignment else None, event, liters)
    _process(factory)
    ev = _event(db_session, ev_id)
    assert ev.result == "rejected" and ev.reject_reason.split(":")[0] == reason
    assert ev.processed_at is not None


def test_events_for_completed_or_cancelled_assignments_rejected(
    client, db_session, factory, machines, order, jefe
):
    a1 = _by_machine(order)["M01"]["id"]
    m1 = machines["M01"]
    _act(client, jefe, a1, "start")
    _act(client, jefe, a1, "complete", actual_liters="70")
    late = _insert(db_session, m1, a1, "progress", "80")
    _process(factory)
    assert _event(db_session, late).result == "rejected"
    db_session.expire_all()
    assert Decimal(db_session.get(Assignment, a1).actual_liters) == Decimal("70.00")


def test_rejected_event_does_not_block_later_ones(client, db_session, factory, machines, order):
    a1 = _by_machine(order)["M01"]["id"]
    m1 = machines["M01"]
    bad = _insert(db_session, m1, a1, "pause", seq=1)
    good = _insert(db_session, m1, a1, "start", seq=2)
    _process(factory)
    assert _event(db_session, bad).result == "rejected"
    assert _event(db_session, good).result == "applied"


def test_error_event_recorded_without_status_change(
    client, db_session, factory, machines, order, jefe
):
    a1 = _by_machine(order)["M01"]["id"]
    m1 = machines["M01"]
    _insert(db_session, m1, a1, "start", seq=1)
    err = _insert(db_session, m1, a1, "error", seq=2, error_code="E42",
                  message="Sensor de nivel")
    _process(factory)
    assert _event(db_session, err).result == "applied"
    db_session.expire_all()
    ae = db_session.query(AssignmentEvent).filter(
        AssignmentEvent.assignment_id == a1, AssignmentEvent.event == "error"
    ).one()
    assert (ae.error_code, ae.message, ae.source) == ("E42", "Sensor de nivel", "plc")
    assert db_session.get(Assignment, a1).status == "running"
    entry = db_session.query(AuditLog).filter(
        AuditLog.entity_id == order["id"], AuditLog.action == "error"
    ).one()
    assert entry.after["error_code"] == "E42" and entry.after["source"] == "plc"
    # Shown on the machine board.
    board = {m["code"]: m for m in client.get(f"{API}/machines/board").json()}
    last = board["M01"]["plc_last_error"]
    assert last["error_code"] == "E42" and last["operation_number"] == order["operation_number"]
    assert board["M04"]["plc_last_error"] is None
    # A machine-level error (no assignment) is accepted and becomes the latest.
    _insert(db_session, m1, None, "error", seq=3, error_code="E1", message="Paro de emergencia")
    _process(factory)
    board = {m["code"]: m for m in client.get(f"{API}/machines/board").json()}
    assert board["M01"]["plc_last_error"]["error_code"] == "E1"
    assert board["M01"]["plc_last_error"]["operation_number"] is None


def test_pause_resume_then_manual_complete(client, db_session, factory, machines, jefe,
                                           cliente, base_calcio, nh_calcio, calcio_stock):
    """Scenario 4 (logic): PLC start + pause -> Pausada; PLC resume -> En proceso;
    the Production manager completes from the platform; both sources in history."""
    m1 = machines["M01"]
    order = _ready_order(client, db_session, jefe, cliente, base_calcio, nh_calcio, machines,
                         split=[(m1, "100")])
    a1 = order["assignments"][0]["id"]
    _insert(db_session, m1, a1, "start", seq=1)
    _insert(db_session, m1, a1, "progress", "40", seq=2)
    _insert(db_session, m1, a1, "pause", seq=3)
    _process(factory)
    assert _order(client, order["id"])["status"] == "paused"
    _insert(db_session, m1, a1, "resume", seq=4)
    _process(factory)
    assert _order(client, order["id"])["status"] == "in_progress"
    _act(client, jefe, a1, "complete", actual_liters="98")
    data = _order(client, order["id"])
    assert data["status"] == "completed"
    assert data["assignments"][0]["last_source"] == "manual"
    history = client.get(f"{API}/orders/{order['id']}/history").json()
    sources = {(h["action"], (h["after"] or {}).get("source")) for h in history}
    assert {("start", "plc"), ("pause", "plc"), ("resume", "plc"),
            ("complete", "manual")} <= sources


def _movements(db_session, order_id) -> list[tuple[str, str, int | None, int | None, Decimal]]:
    db_session.expire_all()
    rows = db_session.query(StockMovement).filter(StockMovement.order_id == order_id).all()
    return sorted(
        (m.type, m.note.split(" — ")[-1] if m.note else "", m.product_id,
         m.packaging_item_id, Decimal(m.quantity))
        for m in rows
    )


def test_plc_completion_moves_stock_exactly_like_manual(
    client, db_session, factory, cliente, base_calcio, nh_calcio, machines, calcio_stock, jefe,
    site,
):
    """Scenario 1 (logic): 1,000 L split 500/500, completed 500 and 495 ->
    Completada, Faltante 5.00 L, in Por cerrar; the same stock movements as a
    manual completion of an identical order."""
    from app.services.stock_service import apply_movement

    apply_movement(db_session, site_id=site.id, item=ItemRef("product", base_calcio.id),
                   movement_type="receipt", quantity=Decimal("1000"), user=None)
    db_session.commit()
    m1, m2 = machines["M01"], machines["M02"]
    split = [(m1, "500"), (m2, "500")]
    plc = _ready_order(client, db_session, jefe, cliente, base_calcio, nh_calcio, machines,
                       liters="1000", split=split)
    manual = _ready_order(client, db_session, jefe, cliente, base_calcio, nh_calcio, machines,
                          liters="1000", split=split)
    p = _by_machine(plc)
    for machine, final in ((m1, "500"), (m2, "495")):
        a = p[machine.code]["id"]
        _insert(db_session, machine, a, "start")
        _insert(db_session, machine, a, "progress", "250")
        _insert(db_session, machine, a, "complete", final)
    _process(factory)
    data = _order(client, plc["id"])
    assert data["status"] == "completed"
    assert Decimal(data["difference"]["difference"]) == Decimal("-5.00")
    to_close = client.get(f"{API}/production/to-close").json()
    assert plc["id"] in {o["id"] for o in to_close}

    mm = _by_machine(manual)
    for code, final in (("M01", "500"), ("M02", "495")):
        _act(client, jefe, mm[code]["id"], "start")
        _act(client, jefe, mm[code]["id"], "complete", actual_liters=final)
    assert _order(client, manual["id"])["status"] == "completed"
    assert _movements(db_session, plc["id"]) == _movements(db_session, manual["id"])
    assert _on_hand(db_session, site.id, ItemRef("product", nh_calcio.id)) == Decimal("1990")


def test_order_without_expiry_cannot_be_started_by_plc(
    client, db_session, factory, cliente, base_calcio, nh_calcio, machines, calcio_stock, jefe
):
    order = _create(client, jefe, cliente.id, [(base_calcio.id, "100")], nh_calcio.id)
    data = _assign(client, jefe, order["id"], [(machines["M01"], "100")])
    assert data["status"] == "created"
    ev = _insert(db_session, machines["M01"], data["assignments"][0]["id"], "start")
    _process(factory)
    assert _event(db_session, ev).result == "rejected"
    _expiry(client, jefe, order["id"], "2029-03-01")  # now it can
    ev = _insert(db_session, machines["M01"], data["assignments"][0]["id"], "start")
    _process(factory)
    assert _event(db_session, ev).result == "applied"


# Credentials / board ---------------------------------------------------------------------


def test_username_for_machine_code():
    assert username_for("M01") == "plc_m01"
    assert username_for("Máq 2-B") == "plc_m_q_2_b"


@pytest.mark.parametrize(
    "role,status", [("admin", 403), ("production_manager", 403), ("master_admin", 409)]
)
def test_plc_credentials_permission(client, db_session, machines, role, status):
    """Only machines.plc_credentials (master admin); on SQLite the master admin
    gets a clear refusal (PostgreSQL only, covered by test_plc_postgres)."""
    headers = login_as(client, db_session, role)
    resp = client.post(f"{API}/machines/{machines['M01'].id}/plc-credentials", headers=headers)
    assert resp.status_code == status, resp.text
    if status == 409:
        assert resp.json()["error"]["code"] == "PLC_CREDENTIALS_UNAVAILABLE"


def test_board_shows_plc_contact(client, db_session, machines, jefe):
    from datetime import UTC, datetime

    m1 = machines["M01"]
    m1.plc_db_username = "plc_m01"
    m1.last_seen_at = datetime(2026, 10, 15, 17, 0, tzinfo=UTC)
    db_session.commit()
    board = {m["code"]: m for m in client.get(f"{API}/machines/board").json()}
    assert board["M01"]["has_plc_login"] is True
    assert board["M01"]["plc_last_seen_at"].startswith("2026-10-15T17:00")
    assert board["M02"]["has_plc_login"] is False and board["M02"]["plc_last_seen_at"] is None
    machine = client.get(f"{API}/machines/{m1.id}").json()
    assert machine["plc_db_username"] == "plc_m01"
