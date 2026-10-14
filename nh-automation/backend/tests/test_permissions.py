"""Permission checks: the role -> permission map (overview §4) and every role on
each permission-gated endpoint that exists so far (allowed vs 403)."""

import pytest

from app.core.permissions import ROLE_PERMISSIONS, Permission, Role
from tests.conftest import login, login_as, make_user

ALL_ROLES = ["master_admin", "admin", "production_manager", "operator"]
M, A, P, OP = "master_admin", "admin", "production_manager", "operator"

# Literal copy of the overview §4 table (v3). Changing the map means changing this.
OVERVIEW_MATRIX: dict[str, set[str]] = {
    "users.manage": {M},
    "catalogs.manage": {M, A},
    "sequences.manage": {M},
    "inventory.view": {M, A, P},
    "inventory.move": {M, A},
    "orders.view": {M, A, P},
    "orders.edit": {M, A, P},
    "orders.comment": {M, A, P},
    "orders.assign": {M, P},
    "orders.expiry": {M, P},
    "orders.traceability": {M, A, P, OP},
    "production.control": {M, A, P, OP},
    "orders.cancel": {M, A, P},
    "orders.close": {M, P},
    "machines.board": {M, A, P},
    "machines.plc_credentials": {M},
    "audit.view": {M},
    "settings.manage": {M},
}


def test_permission_map_matches_overview():
    assert {p.value for p in Permission} == set(OVERVIEW_MATRIX)
    for permission, roles in OVERVIEW_MATRIX.items():
        granted = {r.value for r in Role if Permission(permission) in ROLE_PERMISSIONS[r]}
        assert granted == roles, permission


def test_removed_permissions_and_role_are_gone():
    values = {p.value for p in Permission}
    assert not values & {"orders.approve", "orders.verify", "assignments.work_own"}
    assert "supervisor" not in {r.value for r in Role}


ENDPOINTS_AND_ALLOWED_ROLES = [
    ("GET", "/api/v1/users", {M}),
    ("GET", "/api/v1/audit", {M}),
    ("GET", "/api/v1/settings", {M}),
    ("GET", "/api/v1/order-sequences", {M}),
]


@pytest.mark.parametrize("method,path,allowed_roles", ENDPOINTS_AND_ALLOWED_ROLES)
@pytest.mark.parametrize("role", ALL_ROLES)
def test_endpoint_permission_matrix(client, db_session, method, path, allowed_roles, role):
    username = f"user_{role}"
    make_user(db_session, username=username, role=role, password="pw-1234567")
    login(client, username, "pw-1234567")

    resp = client.request(method, path)

    if role in allowed_roles:
        assert resp.status_code == 200, f"{role} should be allowed on {method} {path}"
    else:
        assert resp.status_code == 403, f"{role} should be forbidden on {method} {path}"


# Catalogs and inventory --------------------------------------------------------

OFFICE = {M, A}
VIEWERS = {M, A, P}  # catalogs.manage or inventory.view

READS = [
    ("/api/v1/products", VIEWERS),
    ("/api/v1/packaging-items", VIEWERS),
    ("/api/v1/razones-sociales", VIEWERS),
    ("/api/v1/clients", VIEWERS),
    ("/api/v1/sites", VIEWERS),
    ("/api/v1/machines", VIEWERS),
    ("/api/v1/inventory", VIEWERS),
    ("/api/v1/inventory/movements", VIEWERS),
    ("/api/v1/inventory/movement-users", VIEWERS),
    ("/api/v1/inventory/alerts", VIEWERS),
    ("/api/v1/imports/products/sources", OFFICE),
    ("/api/v1/orders", VIEWERS),  # orders.view
]


@pytest.mark.parametrize("path,allowed_roles", READS)
@pytest.mark.parametrize("role", ALL_ROLES)
def test_read_permissions(client, db_session, base_catalogs, path, allowed_roles, role):
    login_as(client, db_session, role)
    resp = client.get(path)
    expected = 200 if role in allowed_roles else 403
    assert resp.status_code == expected, f"{role} on GET {path}"


@pytest.mark.parametrize("role", ALL_ROLES)
def test_catalog_writes_need_catalogs_manage(client, db_session, base_catalogs, nb_id, role):
    """Production manager can view catalogs but not edit them; operator has no access."""
    headers = login_as(client, db_session, role)
    expected_create = 201 if role in OFFICE else 403
    resp = client.post(
        "/api/v1/products",
        json={"code": "P1", "name": "P", "provider": "X", "presentation": "1X20",
              "razon_social_id": nb_id},
        headers=headers,
    )
    assert resp.status_code == expected_create
    resp = client.post(
        "/api/v1/razones-sociales", json={"code": "ZZ", "name": "Z"}, headers=headers
    )
    assert resp.status_code == expected_create
    resp = client.patch(
        f"/api/v1/razones-sociales/{nb_id}", json={"name": "NOBELTECH SA"}, headers=headers
    )
    assert resp.status_code == (200 if role in OFFICE else 403)
    resp = client.patch(
        f"/api/v1/sites/{base_catalogs.id}", json={"name": "Renombrado"}, headers=headers
    )
    assert resp.status_code == (200 if role in OFFICE else 403)


@pytest.mark.parametrize("role", ALL_ROLES)
def test_stock_moves_need_inventory_move(client, db_session, base_catalogs, role):
    """inventory.move is master admin + admin only (v3): the Production manager only views."""
    from app.models.catalogs import PackagingItem

    item = db_session.query(PackagingItem).first()
    headers = login_as(client, db_session, role)
    resp = client.post(
        "/api/v1/inventory/receipts",
        json={"item_type": "packaging", "item_id": item.id, "site_id": base_catalogs.id,
              "quantity": "5"},
        headers=headers,
    )
    assert resp.status_code == (201 if role in OFFICE else 403)
    resp = client.post(
        "/api/v1/inventory/adjustments",
        json={"item_type": "packaging", "item_id": item.id, "site_id": base_catalogs.id,
              "counted_quantity": "1", "reason": "conteo"},
        headers=headers,
    )
    assert resp.status_code == (201 if role in OFFICE else 403)


@pytest.mark.parametrize("role", ALL_ROLES)
def test_sequences_writes_need_sequences_manage(client, db_session, base_catalogs, role):
    headers = login_as(client, db_session, role)
    resp = client.patch(
        "/api/v1/order-sequences/trabajo", json={"next_number": 5}, headers=headers
    )
    assert resp.status_code == (200 if role == M else 403)


@pytest.mark.parametrize("role", ALL_ROLES)
def test_order_writes_need_order_permissions(client, db_session, base_catalogs, nb_id, role):
    """orders.edit / orders.comment / orders.cancel: everyone except operators (phase 2)."""
    from decimal import Decimal

    from app.models.catalogs import Client, Product
    from app.services import stock_service

    product = Product(code="P1", name="P", provider="X", presentation="1000",
                      razon_social_id=nb_id, is_active=True)
    cliente = Client(name="C", code="C1", is_active=True)
    db_session.add_all([product, cliente])
    db_session.flush()
    stock_service.apply_movement(
        db_session, site_id=base_catalogs.id, item=stock_service.ItemRef("product", product.id),
        movement_type="receipt", quantity=Decimal("100"), user=None,
    )
    db_session.commit()
    allowed = role in VIEWERS
    headers = login_as(client, db_session, role)
    resp = client.post("/api/v1/orders", json={
        "order_type": "trabajo", "client_id": cliente.id,
        "base_products": [{"product_id": product.id, "liters": "10"}],
        "finished_product_id": product.id,
    }, headers=headers)
    assert resp.status_code == (201 if allowed else 403)
    if not allowed:
        return
    order_id = resp.json()["id"]
    url = f"/api/v1/orders/{order_id}"
    assert client.get(url).status_code == 200
    assert client.patch(url, json={"labels_planned": 1}, headers=headers).status_code == 200
    assert client.post(f"{url}/comments", json={"text": "x"}, headers=headers).status_code == 201
    assert client.get(f"{url}/history").status_code == 200
    assert client.get(f"{url}/print-data").status_code == 200
    assert client.post(f"{url}/cancel", json={"reason": "r"}, headers=headers).status_code == 200


def test_me_returns_production_manager_permissions(client, db_session):
    login_as(client, db_session, P)
    me = client.get("/api/v1/auth/me").json()
    assert me["role"] == P
    assert "orders.close" in me["permissions"]
    assert "inventory.view" in me["permissions"]
    assert "inventory.move" not in me["permissions"]
