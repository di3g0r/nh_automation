"""User CRUD (FR-USR) and the last-master-admin protection (BR-15)."""

from app.core.permissions import Role
from app.models.audit_log import AuditLog
from app.models.user import User
from tests.conftest import auth_headers, login, make_user


def _login_master_admin(client, db_session, username="root_admin"):
    make_user(db_session, username=username, role=Role.MASTER_ADMIN.value, password="pw-1234567")
    login(client, username, "pw-1234567")


def test_create_user(client, db_session):
    _login_master_admin(client, db_session)

    resp = client.post(
        "/api/v1/users",
        json={
            "username": "newop",
            "full_name": "New Operator",
            "role": "operator",
            "password": "operator-pw1",
            "pin": "4321",
        },
        headers=auth_headers(client),
    )

    assert resp.status_code == 201
    body = resp.json()
    assert body["username"] == "newop"
    assert body["has_pin"] is True
    assert body["is_active"] is True


def test_create_user_duplicate_username_rejected(client, db_session):
    _login_master_admin(client, db_session)
    make_user(db_session, username="dup", password="pw-1234567")

    resp = client.post(
        "/api/v1/users",
        json={
            "username": "dup",
            "full_name": "Duplicate",
            "role": "admin",
            "password": "another-pw1",
        },
        headers=auth_headers(client),
    )

    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "USERNAME_TAKEN"


def test_deactivate_user(client, db_session):
    _login_master_admin(client, db_session)
    target = make_user(db_session, username="to_deactivate", password="pw-1234567")

    resp = client.post(f"/api/v1/users/{target.id}/deactivate", headers=auth_headers(client))

    assert resp.status_code == 200
    assert resp.json()["is_active"] is False


def test_deactivated_user_cannot_login_after_api_call(client, db_session):
    _login_master_admin(client, db_session)
    target = make_user(db_session, username="to_deactivate", password="pw-1234567")

    client.post(f"/api/v1/users/{target.id}/deactivate", headers=auth_headers(client))

    resp = login(client, "to_deactivate", "pw-1234567")
    assert resp.status_code == 401


def test_cannot_deactivate_last_active_master_admin(client, db_session):
    _login_master_admin(client, db_session, username="only_master")
    only_master = db_session.query(User).filter(User.username == "only_master").first()

    resp = client.post(f"/api/v1/users/{only_master.id}/deactivate", headers=auth_headers(client))

    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "LAST_MASTER_ADMIN"


def test_can_deactivate_master_admin_when_another_is_active(client, db_session):
    _login_master_admin(client, db_session, username="master_one")
    other = make_user(
        db_session, username="master_two", role=Role.MASTER_ADMIN.value, password="pw-1234567"
    )

    resp = client.post(f"/api/v1/users/{other.id}/deactivate", headers=auth_headers(client))
    assert resp.status_code == 200


def test_cannot_demote_last_active_master_admin(client, db_session):
    _login_master_admin(client, db_session, username="only_master")
    only_master = db_session.query(User).filter(User.username == "only_master").first()

    resp = client.patch(
        f"/api/v1/users/{only_master.id}",
        json={"role": "admin"},
        headers=auth_headers(client),
    )

    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "LAST_MASTER_ADMIN"


def test_reset_credentials(client, db_session):
    _login_master_admin(client, db_session)
    target = make_user(db_session, username="jdoe", password="old-pw-123")

    resp = client.post(
        f"/api/v1/users/{target.id}/reset-credentials",
        json={"password": "brand-new-pw"},
        headers=auth_headers(client),
    )
    assert resp.status_code == 200

    relogin = login(client, "jdoe", "brand-new-pw")
    assert relogin.status_code == 200


def test_create_update_deactivate_write_audit_entries(client, db_session):
    _login_master_admin(client, db_session)

    create_resp = client.post(
        "/api/v1/users",
        json={
            "username": "audited",
            "full_name": "Audited User",
            "role": "admin",
            "password": "audited-pw1",
        },
        headers=auth_headers(client),
    )
    user_id = create_resp.json()["id"]

    client.patch(
        f"/api/v1/users/{user_id}",
        json={"full_name": "Audited User Renamed"},
        headers=auth_headers(client),
    )
    client.post(f"/api/v1/users/{user_id}/deactivate", headers=auth_headers(client))

    entries = (
        db_session.query(AuditLog)
        .filter(AuditLog.entity == "user", AuditLog.entity_id == user_id)
        .order_by(AuditLog.id)
        .all()
    )
    actions = [e.action for e in entries]
    assert actions == ["create", "update", "deactivate"]
    assert entries[0].after["username"] == "audited"
    assert entries[1].before["full_name"] == "Audited User"
    assert entries[1].after["full_name"] == "Audited User Renamed"
    assert entries[2].after["is_active"] is False
