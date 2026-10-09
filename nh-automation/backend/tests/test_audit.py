"""Audit log API (FR-AUD-2): master admin can list/filter; no edit/delete route exists."""

from app.core.permissions import Role
from tests.conftest import auth_headers, login, make_user


def test_audit_log_lists_entries_from_user_actions(client, db_session):
    make_user(db_session, username="root", role=Role.MASTER_ADMIN.value, password="pw-1234567")
    login(client, "root", "pw-1234567")

    client.post(
        "/api/v1/users",
        json={
            "username": "someone",
            "full_name": "Someone",
            "role": "admin",
            "password": "someone-pw1",
        },
        headers=auth_headers(client),
    )

    resp = client.get("/api/v1/audit")

    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] >= 1
    assert any(item["entity"] == "user" and item["action"] == "create" for item in body["items"])


def test_audit_log_filter_by_entity(client, db_session):
    make_user(db_session, username="root", role=Role.MASTER_ADMIN.value, password="pw-1234567")
    login(client, "root", "pw-1234567")

    resp = client.get("/api/v1/audit", params={"entity": "nonexistent_entity"})

    assert resp.status_code == 200
    assert resp.json()["total"] == 0


def test_no_write_endpoints_for_audit_log(client, db_session):
    make_user(db_session, username="root", role=Role.MASTER_ADMIN.value, password="pw-1234567")
    login(client, "root", "pw-1234567")

    resp = client.post("/api/v1/audit", json={}, headers=auth_headers(client))
    assert resp.status_code in (404, 405)
