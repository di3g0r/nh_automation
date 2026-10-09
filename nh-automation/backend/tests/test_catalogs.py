"""Catalogs (FR-CAT-1..6): unique codes, deactivation rules, default site, machine keys, audit."""

from app.core.security import hash_token
from app.models.audit_log import AuditLog
from app.models.catalogs import Machine, PackagingItem, Site
from app.models.settings import Setting
from tests.conftest import login_as

API = "/api/v1"

PRODUCT = {
    "code": "GRN100C1XL20F004",
    "name": "NB-NEEM",
    "provider": "GRN",
    "presentation": "1X20",
    "container_liters": "20",
}


def test_seed_data_present(client, db_session, base_catalogs):
    login_as(client, db_session, "admin")
    sites = client.get(f"{API}/sites").json()
    assert [s["name"] for s in sites["items"]] == ["ECOINDUSTRIAL PACÍFICO"]
    assert sites["items"][0]["is_default"] is True
    assert client.get(f"{API}/clients").json()["total"] == 2
    assert client.get(f"{API}/packaging-items").json()["total"] == 14


def test_create_and_update_product(client, db_session):
    headers = login_as(client, db_session, "admin")
    resp = client.post(f"{API}/products", json=PRODUCT, headers=headers)
    assert resp.status_code == 201
    body = resp.json()
    assert body["container_liters"] == "20.00"
    assert body["is_active"] is True

    resp = client.patch(
        f"{API}/products/{body['id']}", json={"name": "NB-NEEM 2"}, headers=headers
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "NB-NEEM 2"
    assert resp.json()["provider"] == "GRN"  # untouched

    # container_liters is optional and can be cleared explicitly.
    resp = client.patch(
        f"{API}/products/{body['id']}", json={"container_liters": None}, headers=headers
    )
    assert resp.json()["container_liters"] is None


def test_product_code_must_be_unique(client, db_session):
    headers = login_as(client, db_session, "admin")
    assert client.post(f"{API}/products", json=PRODUCT, headers=headers).status_code == 201
    resp = client.post(f"{API}/products", json=PRODUCT, headers=headers)
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "DUPLICATE_CODE"


def test_update_to_existing_code_rejected(client, db_session):
    headers = login_as(client, db_session, "admin")
    client.post(f"{API}/products", json=PRODUCT, headers=headers)
    other = client.post(
        f"{API}/products", json=PRODUCT | {"code": "OTHER"}, headers=headers
    ).json()
    resp = client.patch(
        f"{API}/products/{other['id']}", json={"code": PRODUCT["code"]}, headers=headers
    )
    assert resp.status_code == 409


def test_packaging_and_client_codes_unique(client, db_session, base_catalogs):
    headers = login_as(client, db_session, "admin")
    resp = client.post(
        f"{API}/packaging-items",
        json={"code": "ENVCO01005", "description": "x", "category": "envase"},
        headers=headers,
    )
    assert resp.status_code == 409
    resp = client.post(f"{API}/clients", json={"name": "Otro", "code": "NB"}, headers=headers)
    assert resp.status_code == 409


def test_packaging_category_validated(client, db_session):
    headers = login_as(client, db_session, "admin")
    resp = client.post(
        f"{API}/packaging-items",
        json={"code": "X1", "description": "x", "category": "tarima"},
        headers=headers,
    )
    assert resp.status_code == 422


def test_no_delete_endpoint_deactivate_instead(client, db_session):
    headers = login_as(client, db_session, "admin")
    product = client.post(f"{API}/products", json=PRODUCT, headers=headers).json()

    assert client.delete(f"{API}/products/{product['id']}", headers=headers).status_code == 405

    resp = client.patch(
        f"{API}/products/{product['id']}", json={"is_active": False}, headers=headers
    )
    assert resp.json()["is_active"] is False
    # Still readable (old records keep displaying it).
    assert client.get(f"{API}/products/{product['id']}").status_code == 200
    assert client.get(f"{API}/products?active=true").json()["total"] == 0
    assert client.get(f"{API}/products?active=false").json()["total"] == 1

    actions = [
        a.action for a in db_session.query(AuditLog).filter(AuditLog.entity == "product").all()
    ]
    assert actions == ["create", "deactivate"]


def test_inactive_site_cannot_be_selected_for_machine(client, db_session, base_catalogs):
    headers = login_as(client, db_session, "admin")
    site = client.post(f"{API}/sites", json={"name": "Otra planta"}, headers=headers).json()
    client.patch(f"{API}/sites/{site['id']}", json={"is_active": False}, headers=headers)

    resp = client.post(
        f"{API}/machines",
        json={"code": "M99", "name": "Máquina 99", "site_id": site["id"]},
        headers=headers,
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "INACTIVE_ITEM"


def test_exactly_one_default_site(client, db_session, base_catalogs):
    headers = login_as(client, db_session, "admin")
    original = base_catalogs.id
    new = client.post(
        f"{API}/sites", json={"name": "Planta 2", "is_default": True}, headers=headers
    ).json()
    assert new["is_default"] is True

    db_session.expire_all()
    defaults = db_session.query(Site).filter(Site.is_default.is_(True)).all()
    assert [s.id for s in defaults] == [new["id"]]
    setting = db_session.query(Setting).filter(Setting.key == "default_site_id").one()
    assert setting.value == new["id"]

    # Cannot un-default or deactivate the default site.
    resp = client.patch(f"{API}/sites/{new['id']}", json={"is_default": False}, headers=headers)
    assert resp.status_code == 409
    resp = client.patch(f"{API}/sites/{new['id']}", json={"is_active": False}, headers=headers)
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "DEFAULT_SITE_INACTIVE"

    # Moving the default back is fine.
    resp = client.patch(f"{API}/sites/{original}", json={"is_default": True}, headers=headers)
    assert resp.status_code == 200
    assert client.get(f"{API}/sites/{new['id']}").json()["is_default"] is False


def test_default_site_setting_is_read_only(client, db_session, base_catalogs):
    headers = login_as(client, db_session, "master_admin")
    resp = client.patch(f"{API}/settings/default_site_id", json={"value": 99}, headers=headers)
    assert resp.status_code == 409


def test_machine_key_shown_once_and_stored_hashed(client, db_session, base_catalogs):
    headers = login_as(client, db_session, "admin")
    resp = client.post(
        f"{API}/machines",
        json={"code": "M01", "name": "Máquina 1", "site_id": base_catalogs.id},
        headers=headers,
    )
    assert resp.status_code == 201
    body = resp.json()
    key = body["api_key"]
    machine_id = body["machine"]["id"]
    assert len(key) > 30
    assert body["machine"]["site_name"] == "ECOINDUSTRIAL PACÍFICO"

    stored = db_session.get(Machine, machine_id)
    assert stored.api_key_hash == hash_token(key)
    assert key not in stored.api_key_hash

    # Never returned again.
    got = client.get(f"{API}/machines/{machine_id}").json()
    assert "api_key" not in got
    assert got["has_api_key"] is True

    rotated = client.post(f"{API}/machines/{machine_id}/rotate-key", headers=headers).json()
    assert rotated["api_key"] != key
    db_session.expire_all()
    assert db_session.get(Machine, machine_id).api_key_hash == hash_token(rotated["api_key"])

    # The key (or its hash) never ends up in the audit log.
    for entry in db_session.query(AuditLog).filter(AuditLog.entity == "machine").all():
        dumped = str(entry.before) + str(entry.after)
        assert key not in dumped and rotated["api_key"] not in dumped
        assert hash_token(key) not in dumped


def test_machine_code_unique_and_maintenance_flag(client, db_session, base_catalogs):
    headers = login_as(client, db_session, "admin")
    payload = {"code": "M01", "name": "Máquina 1", "site_id": base_catalogs.id}
    m = client.post(f"{API}/machines", json=payload, headers=headers).json()["machine"]
    assert client.post(f"{API}/machines", json=payload, headers=headers).status_code == 409

    resp = client.patch(
        f"{API}/machines/{m['id']}", json={"in_maintenance": True}, headers=headers
    )
    assert resp.json()["in_maintenance"] is True


def test_catalog_writes_audited(client, db_session, base_catalogs):
    headers = login_as(client, db_session, "admin")
    item = db_session.query(PackagingItem).filter(PackagingItem.code == "ENVCO01005").one()
    client.patch(
        f"{API}/packaging-items/{item.id}", json={"low_stock_threshold": 50}, headers=headers
    )
    entry = (
        db_session.query(AuditLog)
        .filter(AuditLog.entity == "packaging_item", AuditLog.entity_id == item.id)
        .one()
    )
    assert entry.action == "update"
    assert entry.before["low_stock_threshold"] == 0
    assert entry.after["low_stock_threshold"] == 50
