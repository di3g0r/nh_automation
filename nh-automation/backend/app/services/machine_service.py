"""Machine registry (FR-CAT-5).

A machine gets a random API key on creation and on rotation. The plain key is
returned once and only its SHA-256 hash is stored (NFR-1); PLC endpoints
(phase 4) authenticate with `find_by_api_key`.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.security import hash_token, new_token
from app.models.catalogs import Machine, Site
from app.models.user import User
from app.schemas.catalogs import MachineCreate, MachineUpdate
from app.services import audit_service
from app.services.catalog_service import (
    apply_changes,
    ensure_unique,
    get,
    require_active,
)

_FIELDS = ("code", "name", "site_id", "is_active", "in_maintenance")
_KEY_PREFIX = "nhm_"


def _snapshot(m: Machine) -> dict:
    return {f: getattr(m, f) for f in _FIELDS} | {"has_api_key": bool(m.api_key_hash)}


def _new_key() -> tuple[str, str]:
    raw = _KEY_PREFIX + new_token(32)
    return raw, hash_token(raw)


def find_by_api_key(db: Session, raw_key: str) -> Machine | None:
    return db.query(Machine).filter(Machine.api_key_hash == hash_token(raw_key)).first()


def create_machine(db: Session, data: MachineCreate, *, actor: User) -> tuple[Machine, str]:
    ensure_unique(
        db, Machine, Machine.code, data.code, message="Ya existe una máquina con ese código."
    )
    require_active(get(db, Site, data.site_id), "El sitio")
    raw, hashed = _new_key()
    machine = Machine(
        code=data.code,
        name=data.name,
        site_id=data.site_id,
        in_maintenance=data.in_maintenance,
        is_active=True,
        api_key_hash=hashed,
    )
    db.add(machine)
    db.flush()
    audit_service.record(
        db, user=actor, entity="machine", entity_id=machine.id, action="create",
        before=None, after=_snapshot(machine),
    )
    db.commit()
    db.refresh(machine)
    return machine, raw


def update_machine(db: Session, machine_id: int, data: MachineUpdate, *, actor: User) -> Machine:
    machine = get(db, Machine, machine_id)
    before = _snapshot(machine)
    if data.code is not None:
        ensure_unique(
            db, Machine, Machine.code, data.code, exclude_id=machine.id,
            message="Ya existe una máquina con ese código.",
        )
    if data.site_id is not None and data.site_id != machine.site_id:
        require_active(get(db, Site, data.site_id), "El sitio")
    apply_changes(machine, data)
    db.flush()
    after = _snapshot(machine)
    if after != before:
        action = "update"
        if before["is_active"] and not after["is_active"]:
            action = "deactivate"
        elif not before["is_active"] and after["is_active"]:
            action = "activate"
        audit_service.record(
            db, user=actor, entity="machine", entity_id=machine.id, action=action,
            before=before, after=after,
        )
    db.commit()
    db.refresh(machine)
    return machine


def rotate_key(db: Session, machine_id: int, *, actor: User) -> tuple[Machine, str]:
    machine = get(db, Machine, machine_id)
    raw, hashed = _new_key()
    machine.api_key_hash = hashed
    db.flush()
    # Never log the key or its hash; only the fact that it was rotated.
    audit_service.record(
        db, user=actor, entity="machine", entity_id=machine.id, action="rotate_key",
        before={"code": machine.code}, after={"code": machine.code},
    )
    db.commit()
    db.refresh(machine)
    return machine, raw
