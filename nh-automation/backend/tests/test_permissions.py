"""Permission checks: each role on each phase-0 endpoint (allowed vs 403)."""

import pytest

from tests.conftest import login, login_as, make_user

ENDPOINTS_AND_ALLOWED_ROLES = [
    ("GET", "/api/v1/users", {"master_admin"}),
    ("GET", "/api/v1/audit", {"master_admin"}),
    ("GET", "/api/v1/settings", {"master_admin"}),
]

ALL_ROLES = ["master_admin", "admin", "supervisor", "operator"]


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


# Phase 1: catalogs and inventory ---------------------------------------------

OFFICE = {"master_admin", "admin"}
STOCK = {"master_admin", "admin", "supervisor"}

PHASE1_READS = [
    ("/api/v1/products", STOCK),
    ("/api/v1/packaging-items", STOCK),
    ("/api/v1/clients", STOCK),
    ("/api/v1/sites", STOCK),
    ("/api/v1/machines", STOCK),
    ("/api/v1/inventory", STOCK),
    ("/api/v1/inventory/movements", STOCK),
    ("/api/v1/inventory/alerts", STOCK),
    ("/api/v1/imports/products/sources", OFFICE),
]


@pytest.mark.parametrize("path,allowed_roles", PHASE1_READS)
@pytest.mark.parametrize("role", ALL_ROLES)
def test_phase1_read_permissions(client, db_session, base_catalogs, path, allowed_roles, role):
    login_as(client, db_session, role)
    resp = client.get(path)
    expected = 200 if role in allowed_roles else 403
    assert resp.status_code == expected, f"{role} on GET {path}"


@pytest.mark.parametrize("role", ALL_ROLES)
def test_catalog_writes_need_catalogs_manage(client, db_session, base_catalogs, role):
    """Supervisor can move stock but not edit catalogs; operator has no access."""
    headers = login_as(client, db_session, role)
    resp = client.post(
        "/api/v1/products",
        json={"code": "P1", "name": "P", "provider": "X", "presentation": "1X20"},
        headers=headers,
    )
    assert resp.status_code == (201 if role in OFFICE else 403)
    resp = client.patch(
        f"/api/v1/sites/{base_catalogs.id}", json={"name": "Renombrado"}, headers=headers
    )
    assert resp.status_code == (200 if role in OFFICE else 403)


@pytest.mark.parametrize("role", ALL_ROLES)
def test_stock_moves_need_inventory_move(client, db_session, base_catalogs, role):
    from app.models.catalogs import PackagingItem

    item = db_session.query(PackagingItem).first()
    headers = login_as(client, db_session, role)
    resp = client.post(
        "/api/v1/inventory/receipts",
        json={"item_type": "packaging", "item_id": item.id, "site_id": base_catalogs.id,
              "quantity": "5"},
        headers=headers,
    )
    assert resp.status_code == (201 if role in STOCK else 403)
    resp = client.post(
        "/api/v1/inventory/adjustments",
        json={"item_type": "packaging", "item_id": item.id, "site_id": base_catalogs.id,
              "counted_quantity": "1", "reason": "conteo"},
        headers=headers,
    )
    assert resp.status_code == (201 if role in STOCK else 403)
