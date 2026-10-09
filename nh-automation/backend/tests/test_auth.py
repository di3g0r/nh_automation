from datetime import timedelta

from app.core.timezone import utc_now
from tests.conftest import auth_headers, login, make_user


def test_login_success_sets_cookies(client, db_session):
    make_user(db_session, username="jdoe", password="s3cret-pw")

    resp = login(client, "jdoe", "s3cret-pw")

    assert resp.status_code == 200
    assert resp.json()["username"] == "jdoe"
    assert "nh_session" in resp.cookies
    assert "nh_csrf" in resp.cookies


def test_login_wrong_password_fails(client, db_session):
    make_user(db_session, username="jdoe", password="s3cret-pw")

    resp = login(client, "jdoe", "wrong-password")

    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "INVALID_CREDENTIALS"


def test_login_unknown_user_fails(client, db_session):
    resp = login(client, "ghost", "whatever123")
    assert resp.status_code == 401


def test_lockout_after_5_failed_attempts(client, db_session):
    make_user(db_session, username="jdoe", password="s3cret-pw")

    for _ in range(5):
        resp = login(client, "jdoe", "wrong-password")
        assert resp.status_code == 401

    resp = login(client, "jdoe", "s3cret-pw")  # even the correct password now
    assert resp.status_code == 423
    assert resp.json()["error"]["code"] == "ACCOUNT_LOCKED"


def test_lockout_clears_after_window(client, db_session):
    user = make_user(db_session, username="jdoe", password="s3cret-pw")

    for _ in range(5):
        login(client, "jdoe", "wrong-password")

    # Simulate the 15-minute lockout window having passed.
    user.locked_until = utc_now() - timedelta(minutes=1)
    db_session.commit()

    resp = login(client, "jdoe", "s3cret-pw")
    assert resp.status_code == 200


def test_pin_login_success(client, db_session):
    make_user(db_session, username="op1", role="operator", password="unused-pw", pin="1234")

    resp = client.post("/api/v1/auth/pin-login", json={"username": "op1", "pin": "1234"})

    assert resp.status_code == 200
    assert resp.json()["role"] == "operator"


def test_pin_login_wrong_pin_fails(client, db_session):
    make_user(db_session, username="op1", role="operator", password="unused-pw", pin="1234")

    resp = client.post("/api/v1/auth/pin-login", json={"username": "op1", "pin": "9999"})

    assert resp.status_code == 401


def test_deactivated_user_cannot_login(client, db_session):
    make_user(db_session, username="jdoe", password="s3cret-pw", is_active=False)

    resp = login(client, "jdoe", "s3cret-pw")
    assert resp.status_code == 401


def test_me_requires_session(client, db_session):
    resp = client.get("/api/v1/auth/me")
    assert resp.status_code == 401


def test_me_returns_permissions(client, db_session):
    make_user(db_session, username="jdoe", role="admin", password="s3cret-pw")
    login(client, "jdoe", "s3cret-pw")

    resp = client.get("/api/v1/auth/me")

    assert resp.status_code == 200
    body = resp.json()
    assert body["role"] == "admin"
    assert "users.manage" not in body["permissions"]
    assert "orders.edit" in body["permissions"]


def test_logout_without_csrf_header_is_rejected(client, db_session):
    make_user(db_session, username="jdoe", password="s3cret-pw")
    login(client, "jdoe", "s3cret-pw")

    resp = client.post("/api/v1/auth/logout")  # no X-CSRF-Token header

    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "CSRF_INVALID"


def test_logout_with_csrf_header_succeeds_and_invalidates_session(client, db_session):
    make_user(db_session, username="jdoe", password="s3cret-pw")
    login(client, "jdoe", "s3cret-pw")

    resp = client.post("/api/v1/auth/logout", headers=auth_headers(client))
    assert resp.status_code == 200

    resp2 = client.get("/api/v1/auth/me")
    assert resp2.status_code == 401


def test_session_expiry_rejected(client, db_session):
    make_user(db_session, username="jdoe", password="s3cret-pw")
    login(client, "jdoe", "s3cret-pw")

    # Force every open session to look expired.
    from app.models.session import UserSession

    for session in db_session.query(UserSession).all():
        session.expires_at = utc_now() - timedelta(seconds=1)
    db_session.commit()

    resp = client.get("/api/v1/auth/me")
    assert resp.status_code == 401


def test_change_password_requires_current_password(client, db_session):
    make_user(db_session, username="jdoe", password="old-password")
    login(client, "jdoe", "old-password")

    resp = client.post(
        "/api/v1/auth/change-password",
        json={"current_password": "wrong", "new_password": "new-password-1"},
        headers=auth_headers(client),
    )
    assert resp.status_code == 401


def test_change_password_success_allows_relogin(client, db_session):
    make_user(db_session, username="jdoe", password="old-password")
    login(client, "jdoe", "old-password")

    resp = client.post(
        "/api/v1/auth/change-password",
        json={"current_password": "old-password", "new_password": "brand-new-pw"},
        headers=auth_headers(client),
    )
    assert resp.status_code == 200

    relogin = login(client, "jdoe", "brand-new-pw")
    assert relogin.status_code == 200
