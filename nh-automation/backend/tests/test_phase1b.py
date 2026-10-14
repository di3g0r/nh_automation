"""Phase 1b: production_manager role, razones sociales, order sequences, product
razón social (forms and import), seed corrections, tolerance settings."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError

from app.models.audit_log import AuditLog
from app.models.catalogs import Client, Product, RazonSocial
from app.models.user import User
from app.services import seed_service
from tests.conftest import login_as, make_user

API = "/api/v1"
MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "migrations" / "versions" / "c7d2f4a8b913_phase1b_v2_updates.py"
)


def _rs_id(db_session, code: str) -> int:
    return db_session.query(RazonSocial).filter(RazonSocial.code == code).one().id


def _audit(db_session, entity: str) -> list[AuditLog]:
    return db_session.query(AuditLog).filter(AuditLog.entity == entity).order_by(AuditLog.id).all()


# Roles -------------------------------------------------------------------------


def test_migration_converts_supervisor_users():
    spec = importlib.util.spec_from_file_location("phase1b_migration", MIGRATION)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    engine = create_engine("sqlite+pysqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE users (id INTEGER PRIMARY KEY, role VARCHAR(32))"))
        conn.execute(text(
            "INSERT INTO users (role) VALUES ('supervisor'), ('admin'), ('supervisor')"
        ))
        assert module.convert_roles(conn, "supervisor", "production_manager") == 2
        roles = [r for (r,) in conn.execute(text("SELECT role FROM users ORDER BY id"))]
    assert roles == ["production_manager", "admin", "production_manager"]


def test_supervisor_role_rejected_by_api_and_database(client, db_session):
    headers = login_as(client, db_session, "master_admin")
    payload = {"username": "viejo", "full_name": "Viejo", "role": "supervisor",
               "password": "password-123"}
    assert client.post(f"{API}/users", json=payload, headers=headers).status_code == 422
    resp = client.post(
        f"{API}/users", json=payload | {"role": "production_manager"}, headers=headers
    )
    assert resp.status_code == 201
    assert resp.json()["role"] == "production_manager"

    with pytest.raises(IntegrityError):
        make_user(db_session, username="legacy", role="supervisor")
    db_session.rollback()


# Razones sociales ----------------------------------------------------------------


def test_razon_social_crud_and_audit(client, db_session, base_catalogs):
    headers = login_as(client, db_session, "admin")
    resp = client.post(
        f"{API}/razones-sociales", json={"code": " agr5 ", "name": "Agro Cinco"}, headers=headers
    )
    assert resp.status_code == 201, resp.text
    rs = resp.json()
    assert rs["code"] == "AGR5"  # normalized to uppercase
    assert rs["is_active"] is True

    resp = client.patch(
        f"{API}/razones-sociales/{rs['id']}", json={"name": "Agro Cinco SA"}, headers=headers
    )
    assert resp.json()["name"] == "Agro Cinco SA"
    resp = client.patch(
        f"{API}/razones-sociales/{rs['id']}", json={"is_active": False}, headers=headers
    )
    assert resp.json()["is_active"] is False

    actions = [a.action for a in _audit(db_session, "razon_social")]
    assert actions == ["create", "update", "deactivate"]
    assert client.get(f"{API}/razones-sociales?active=true").json()["total"] == 4


def test_razon_social_code_unique_and_format(client, db_session, base_catalogs):
    headers = login_as(client, db_session, "admin")
    resp = client.post(f"{API}/razones-sociales", json={"code": "nb", "name": "X"}, headers=headers)
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "DUPLICATE_CODE"
    for bad in ("ABCDEFG", "N-B", "N B", ""):
        resp = client.post(
            f"{API}/razones-sociales", json={"code": bad, "name": "X"}, headers=headers
        )
        assert resp.status_code == 422, bad
    rs3 = _rs_id(db_session, "RS3")
    resp = client.patch(f"{API}/razones-sociales/{rs3}", json={"code": "ANB"}, headers=headers)
    assert resp.status_code == 409


# Order sequences -----------------------------------------------------------------


def test_sequences_seeded_and_master_admin_can_change(client, db_session, base_catalogs):
    headers = login_as(client, db_session, "master_admin")
    rows = client.get(f"{API}/order-sequences").json()
    assert [(r["order_type"], r["prefix"], r["next_number"]) for r in rows] == [
        ("trabajo", "T", 1),
        ("retrabajo", "R", 1),
    ]

    resp = client.patch(
        f"{API}/order-sequences/trabajo", json={"next_number": 448}, headers=headers
    )
    assert resp.status_code == 200
    assert resp.json()["next_number"] == 448
    entry = _audit(db_session, "order_sequence")[-1]
    assert entry.before["next_number"] == 1
    assert entry.after["next_number"] == 448

    for bad in (0, -5):
        resp = client.patch(
            f"{API}/order-sequences/retrabajo", json={"next_number": bad}, headers=headers
        )
        assert resp.status_code == 422
    resp = client.patch(f"{API}/order-sequences/otro", json={"next_number": 2}, headers=headers)
    assert resp.status_code == 422


def test_admin_cannot_change_sequences(client, db_session, base_catalogs):
    headers = login_as(client, db_session, "admin")
    resp = client.patch(
        f"{API}/order-sequences/trabajo", json={"next_number": 10}, headers=headers
    )
    assert resp.status_code == 403
    assert client.get(f"{API}/order-sequences").status_code == 403


# Products ------------------------------------------------------------------------

PRODUCT = {"code": "P-001", "name": "Producto", "provider": "GRN", "presentation": "1X20"}


def test_product_requires_razon_social(client, db_session, base_catalogs):
    headers = login_as(client, db_session, "admin")
    assert client.post(f"{API}/products", json=PRODUCT, headers=headers).status_code == 422
    resp = client.post(
        f"{API}/products", json=PRODUCT | {"razon_social_id": 9999}, headers=headers
    )
    assert resp.status_code == 404

    rs3 = _rs_id(db_session, "RS3")
    client.patch(f"{API}/razones-sociales/{rs3}", json={"is_active": False}, headers=headers)
    resp = client.post(f"{API}/products", json=PRODUCT | {"razon_social_id": rs3}, headers=headers)
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "INACTIVE_ITEM"

    nb = _rs_id(db_session, "NB")
    resp = client.post(f"{API}/products", json=PRODUCT | {"razon_social_id": nb}, headers=headers)
    assert resp.status_code == 201
    body = resp.json()
    assert (body["razon_social_code"], body["razon_social_name"]) == ("NB", "NOBELTECH")

    # Edit: can change it, cannot clear it, and omitting it keeps it.
    anb = _rs_id(db_session, "ANB")
    resp = client.patch(
        f"{API}/products/{body['id']}", json={"razon_social_id": anb}, headers=headers
    )
    assert resp.json()["razon_social_code"] == "ANB"
    resp = client.patch(
        f"{API}/products/{body['id']}", json={"razon_social_id": None}, headers=headers
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "RAZON_SOCIAL_REQUIRED"
    resp = client.patch(f"{API}/products/{body['id']}", json={"name": "Otro"}, headers=headers)
    assert resp.json()["razon_social_code"] == "ANB"

    entry = _audit(db_session, "product")[-2]  # the razón social change
    assert (entry.before["razon_social_id"], entry.after["razon_social_id"]) == (nb, anb)


def test_product_list_razon_social_filters(client, db_session, base_catalogs):
    nb, anb = _rs_id(db_session, "NB"), _rs_id(db_session, "ANB")
    db_session.add_all([
        Product(code="A", name="A", provider="X", presentation="1", razon_social_id=nb),
        Product(code="B", name="B", provider="X", presentation="1", razon_social_id=anb),
        Product(code="C", name="C", provider="X", presentation="1"),  # imported, none
    ])
    db_session.commit()
    login_as(client, db_session, "production_manager")

    def codes(query: str) -> list[str]:
        return [p["code"] for p in client.get(f"{API}/products{query}").json()["items"]]

    assert codes("") == ["A", "B", "C"]
    assert codes(f"?razon_social_id={anb}") == ["B"]
    assert codes("?without_razon_social=true") == ["C"]
    assert client.get(f"{API}/products?without_razon_social=true").json()["items"][0][
        "razon_social_code"
    ] is None


# Import ------------------------------------------------------------------------

CSV_HEADER = "Código,Nombre,Proveedor,Presentación,Razón social\n"


def _import(client, headers, step, csv_text, mode="create_only"):
    return client.post(
        f"{API}/imports/products/{step}",
        data={"source": "file", "mode": mode},
        files={"file": ("p.csv", csv_text.encode(), "text/csv")},
        headers=headers,
    )


def test_import_valid_razon_social_code(client, db_session, base_catalogs):
    headers = login_as(client, db_session, "admin")
    csv_text = CSV_HEADER + "P1,Uno,GRN,1X20,NB\nP2,Dos,QVR,1000,anb\n"
    resp = _import(client, headers, "confirm", csv_text)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["columns"]["Razón social"] == "razon_social"
    assert [r["values"]["razon_social"] for r in body["rows"]] == ["NB", "ANB"]
    assert not any(r["warnings"] for r in body["rows"])
    db_session.expire_all()
    got = {p.code: p.razon_social.code for p in db_session.query(Product).all()}
    assert got == {"P1": "NB", "P2": "ANB"}


@pytest.mark.parametrize("header", ["razon_social", "RS", "Empresa", "razón social"])
def test_import_razon_social_aliases(client, db_session, base_catalogs, header):
    headers = login_as(client, db_session, "admin")
    csv_text = f"codigo,nombre,proveedor,presentacion,{header}\nP1,Uno,GRN,1X20,NB\n"
    body = _import(client, headers, "preview", csv_text).json()
    assert body["columns"][header] == "razon_social"


def test_import_unknown_razon_social_is_error_and_saves_nothing(
    client, db_session, base_catalogs
):
    headers = login_as(client, db_session, "admin")
    csv_text = CSV_HEADER + "P1,Uno,GRN,1X20,NB\nP2,Dos,GRN,1X20,XYZ\n"
    preview = _import(client, headers, "preview", csv_text).json()
    assert preview["has_errors"] is True
    assert preview["rows"][1]["action"] == "error"
    assert "XYZ" in preview["rows"][1]["errors"][0]

    resp = _import(client, headers, "confirm", csv_text)
    assert resp.status_code == 422
    assert db_session.query(Product).count() == 0


def test_import_inactive_razon_social_is_error(client, db_session, base_catalogs):
    rs = db_session.query(RazonSocial).filter(RazonSocial.code == "RS4").one()
    rs.is_active = False
    db_session.commit()
    headers = login_as(client, db_session, "admin")
    body = _import(client, headers, "preview", CSV_HEADER + "P1,Uno,GRN,1X20,RS4\n").json()
    assert body["rows"][0]["action"] == "error"


def test_import_empty_razon_social_is_warning(client, db_session, base_catalogs):
    headers = login_as(client, db_session, "admin")
    csv_text = CSV_HEADER + "P1,Uno,GRN,1X20,\n"
    body = _import(client, headers, "confirm", csv_text).json()
    row = body["rows"][0]
    assert row["action"] == "create"
    assert any("Sin razón social" in w for w in row["warnings"])
    db_session.expire_all()
    assert db_session.query(Product).one().razon_social_id is None


def test_import_upsert_empty_never_clears_razon_social(client, db_session, base_catalogs):
    headers = login_as(client, db_session, "admin")
    _import(client, headers, "confirm", CSV_HEADER + "P1,Uno,GRN,1X20,NB\n")

    body = _import(
        client, headers, "confirm", CSV_HEADER + "P1,Uno nuevo,GRN,1X20,\n", mode="upsert"
    ).json()
    row = body["rows"][0]
    assert row["action"] == "update"
    assert not any("Sin razón social" in w for w in row["warnings"])  # it keeps NB
    db_session.expire_all()
    p = db_session.query(Product).one()
    assert (p.name, p.razon_social.code) == ("Uno nuevo", "NB")

    # A non-empty code does change it.
    _import(client, headers, "confirm", CSV_HEADER + "P1,Uno nuevo,GRN,1X20,ANB\n", mode="upsert")
    db_session.expire_all()
    assert db_session.query(Product).one().razon_social.code == "ANB"


def test_sample_csv_imports(client, db_session, base_catalogs):
    sample = Path(__file__).resolve().parents[2] / "tools" / "samples" / "productos_ejemplo.csv"
    headers = login_as(client, db_session, "admin")
    resp = client.post(
        f"{API}/imports/products/confirm",
        data={"source": "file", "mode": "create_only"},
        files={"file": (sample.name, sample.read_bytes(), "text/csv")},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    db_session.expire_all()
    products = db_session.query(Product).all()
    assert len(products) == 4
    assert all(p.razon_social is not None for p in products)


# Seeds -------------------------------------------------------------------------


def test_base_catalogs_have_no_clients(db_session, base_catalogs):
    assert db_session.query(Client).count() == 0
    assert {r.code for r in db_session.query(RazonSocial).all()} == {"NB", "ANB", "RS3", "RS4"}


def test_seed_dev(db_session):
    seed_service.seed_dev(db_session)
    seed_service.seed_dev(db_session)  # idempotent
    roles = {u.username: u.role for u in db_session.query(User).all()}
    assert roles["jefe"] == "production_manager"
    assert set(roles.values()) == {"master_admin", "admin", "production_manager"}  # no operator
    products = {p.code: p.razon_social.code for p in db_session.query(Product).all()}
    assert products == {
        "GRN100C1XL20F004": "NB",
        "QVR200C1XL09M01": "ANB",
        "QVR200C1XL20F003": "ANB",
    }
    clients = db_session.query(Client).all()
    assert len(clients) == 2
    assert all("(dev)" in c.name for c in clients)


# Settings ----------------------------------------------------------------------


def test_tolerance_settings_validation(client, db_session):
    headers = login_as(client, db_session, "master_admin")
    keys = {s["key"]: s["value"] for s in client.get(f"{API}/settings").json()}
    assert keys["difference_tolerance_liters"] == 0
    assert keys["difference_tolerance_percent"] == 0

    def patch(key, value):
        return client.patch(f"{API}/settings/{key}", json={"value": value}, headers=headers)

    assert patch("difference_tolerance_percent", 2.5).json()["value"] == 2.5
    assert patch("difference_tolerance_percent", "100").json()["value"] == 100
    assert patch("difference_tolerance_liters", 20).json()["value"] == 20
    for bad in (100.01, -1, 1.234, "abc", None, True):
        resp = patch("difference_tolerance_percent", bad)
        assert resp.status_code == 422, bad
        assert resp.json()["error"]["code"] == "INVALID_SETTING"
    assert patch("difference_tolerance_liters", -0.5).status_code == 422


def test_approver_must_differ_is_gone(client, db_session):
    headers = login_as(client, db_session, "master_admin")
    keys = {s["key"] for s in client.get(f"{API}/settings").json()}
    assert "approver_must_differ" not in keys
    resp = client.patch(
        f"{API}/settings/approver_must_differ", json={"value": True}, headers=headers
    )
    assert resp.status_code == 404
