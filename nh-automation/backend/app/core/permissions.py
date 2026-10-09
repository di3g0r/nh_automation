"""Role -> permission map (overview §4). The single source of truth for authorization.

Endpoints depend on a *permission* (via `require_permission` in app/api/deps.py),
never on a role directly. Only the permissions actually used by phase 0 endpoints
are enforced today (users.manage, audit.view, settings.manage); the rest of the
map is defined here now because it is shared, static configuration -- not a
feature of a later phase -- so later phases just import it.
"""

from __future__ import annotations

from enum import StrEnum


class Role(StrEnum):
    MASTER_ADMIN = "master_admin"
    ADMIN = "admin"
    SUPERVISOR = "supervisor"
    OPERATOR = "operator"


class Permission(StrEnum):
    USERS_MANAGE = "users.manage"
    CATALOGS_MANAGE = "catalogs.manage"
    INVENTORY_VIEW = "inventory.view"
    INVENTORY_MOVE = "inventory.move"
    ORDERS_VIEW = "orders.view"
    ORDERS_EDIT = "orders.edit"
    ORDERS_APPROVE = "orders.approve"
    ORDERS_ASSIGN = "orders.assign"
    ORDERS_TRACEABILITY = "orders.traceability"
    ORDERS_VERIFY = "orders.verify"
    ORDERS_CANCEL = "orders.cancel"
    ASSIGNMENTS_WORK_OWN = "assignments.work_own"
    MACHINES_BOARD = "machines.board"
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
            Permission.ORDERS_APPROVE,
            Permission.ORDERS_ASSIGN,
            Permission.ORDERS_TRACEABILITY,
            Permission.ORDERS_CANCEL,
            Permission.ASSIGNMENTS_WORK_OWN,
            Permission.MACHINES_BOARD,
        }
    ),
    Role.SUPERVISOR: frozenset(
        {
            Permission.INVENTORY_VIEW,
            Permission.INVENTORY_MOVE,
            Permission.ORDERS_VIEW,
            Permission.ORDERS_ASSIGN,
            Permission.ORDERS_TRACEABILITY,
            Permission.ORDERS_VERIFY,
            Permission.ASSIGNMENTS_WORK_OWN,
            Permission.MACHINES_BOARD,
        }
    ),
    Role.OPERATOR: frozenset({Permission.ASSIGNMENTS_WORK_OWN}),
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
