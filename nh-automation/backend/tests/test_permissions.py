"""Permission checks: each role on each phase-0 endpoint (allowed vs 403)."""

import pytest

from tests.conftest import login, make_user

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
