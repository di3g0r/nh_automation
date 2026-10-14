"""Role -> permission map (overview §4). The single source of truth for authorization.

Endpoints depend on a *permission* (via `require_permission` in app/api/deps.py),
never on a role directly. The whole map is defined here; permissions without an
endpoint yet (machines.plc_credentials) are wired by the phase that adds those
routes.
"""

from __future__ import annotations

from enum import StrEnum


class Role(StrEnum):
    MASTER_ADMIN = "master_admin"
    ADMIN = "admin"
    PRODUCTION_MANAGER = "production_manager"  # Jefe de producción (replaces supervisor, v3)
    # Legacy (v3.1): operators do not use the platform. Kept only so old rows
    # stay valid under ck_users_role; such users cannot log in.
    OPERATOR = "operator"


# Roles that can be given to a user (create/edit) and that can log in.
PLATFORM_ROLES = frozenset({Role.MASTER_ADMIN, Role.ADMIN, Role.PRODUCTION_MANAGER})


class Permission(StrEnum):
    USERS_MANAGE = "users.manage"
    CATALOGS_MANAGE = "catalogs.manage"
    SEQUENCES_MANAGE = "sequences.manage"
    INVENTORY_VIEW = "inventory.view"
    INVENTORY_MOVE = "inventory.move"
    ORDERS_VIEW = "orders.view"
    ORDERS_EDIT = "orders.edit"
    ORDERS_COMMENT = "orders.comment"
    ORDERS_ASSIGN = "orders.assign"
    ORDERS_EXPIRY = "orders.expiry"
    ORDERS_TRACEABILITY = "orders.traceability"
    PRODUCTION_CONTROL = "production.control"
    ORDERS_CANCEL = "orders.cancel"
    ORDERS_CLOSE = "orders.close"
    MACHINES_BOARD = "machines.board"
    MACHINES_PLC_CREDENTIALS = "machines.plc_credentials"
    AUDIT_VIEW = "audit.view"
    SETTINGS_MANAGE = "settings.manage"


ROLE_PERMISSIONS: dict[Role, frozenset[Permission]] = {
    Role.MASTER_ADMIN: frozenset(Permission),
    Role.ADMIN: frozenset(
        {
            Permission.CATALOGS_MANAGE,
            Permission.INVENTORY_VIEW,
            Permission.INVENTORY_MOVE,
            Permission.ORDERS_VIEW,
            Permission.ORDERS_EDIT,
            Permission.ORDERS_COMMENT,
            Permission.ORDERS_TRACEABILITY,
            Permission.ORDERS_CANCEL,
            Permission.MACHINES_BOARD,
        }
    ),
    Role.PRODUCTION_MANAGER: frozenset(
        {
            Permission.INVENTORY_VIEW,
            Permission.ORDERS_VIEW,
            Permission.ORDERS_EDIT,
            Permission.ORDERS_COMMENT,
            Permission.ORDERS_ASSIGN,
            Permission.ORDERS_EXPIRY,
            Permission.ORDERS_TRACEABILITY,
            Permission.PRODUCTION_CONTROL,
            Permission.ORDERS_CANCEL,
            Permission.ORDERS_CLOSE,
            Permission.MACHINES_BOARD,
        }
    ),
    Role.OPERATOR: frozenset(),  # legacy, cannot log in (v3.1)
}


def role_has_permission(role: str, permission: Permission) -> bool:
    try:
        role_enum = Role(role)
    except ValueError:
        return False
    return permission in ROLE_PERMISSIONS.get(role_enum, frozenset())


def permissions_for_role(role: str) -> frozenset[Permission]:
    try:
        role_enum = Role(role)
    except ValueError:
        return frozenset()
    return ROLE_PERMISSIONS.get(role_enum, frozenset())
