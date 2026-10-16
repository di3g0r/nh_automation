"""PLC database logins (phase 4, permission `machines.plc_credentials`).

Each machine's PLC logs into PostgreSQL with its own role, member of the
`plc_machine` group role created by the phase-4 migration. That group can
only read the PLC views and insert into `plc_events` (column list), so a PLC
can never read or change business tables.

The app's database user creates and rotates these roles itself (the Docker
image's POSTGRES_USER is a superuser; see DECISIONS 2026-10-15). The password
is generated here, returned once and never stored by the app (PostgreSQL
keeps only its SCRAM hash). Creation and rotation are audited without it.
"""

from __future__ import annotations

import re
import secrets
import string
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError
from app.models.catalogs import Machine
from app.models.user import User
from app.services import audit_service
from app.services.catalog_service import get

GROUP_ROLE = "plc_machine"
CONNECTION_LIMIT = 3
STATEMENT_TIMEOUT = "5s"
_ALPHABET = string.ascii_letters + string.digits
_PASSWORD_LENGTH = 24
_ROLE_RE = re.compile(r"^[a-z][a-z0-9_]{0,62}$")


@dataclass(frozen=True)
class PlcCredentials:
    machine: Machine
    username: str
    password: str
    created: bool  # False = rotated
    host: str
    port: int
    database: str


def username_for(code: str) -> str:
    """`plc_` + the machine code in lowercase, non [a-z0-9] -> `_` (e.g. plc_m01)."""
    slug = re.sub(r"[^a-z0-9]+", "_", code.lower()).strip("_") or "maquina"
    return f"plc_{slug}"[:63]


def _new_password() -> str:
    # Letters and digits only: safe inside a SQL literal and easy to type on a PLC.
    return "".join(secrets.choice(_ALPHABET) for _ in range(_PASSWORD_LENGTH))


def _require_postgres(db: Session) -> None:
    if db.get_bind().dialect.name != "postgresql":
        raise AppError(
            "PLC_CREDENTIALS_UNAVAILABLE",
            "Las credenciales PLC solo se pueden crear con la base de datos PostgreSQL.",
            409,
        )
    can = db.execute(
        text("SELECT rolsuper OR rolcreaterole FROM pg_roles WHERE rolname = current_user")
    ).scalar()
    if not can:
        raise AppError(
            "PLC_CREDENTIALS_UNAVAILABLE",
            "El usuario de la base de datos de la aplicación no puede crear usuarios. "
            "Pida al encargado de TI que cree el usuario del PLC.",
            409,
        )


def _role_exists(db: Session, username: str) -> bool:
    return bool(
        db.execute(text("SELECT 1 FROM pg_roles WHERE rolname = :n"), {"n": username}).scalar()
    )


def create_or_rotate(db: Session, machine_id: int, *, actor: User) -> PlcCredentials:
    """Create the machine's PLC login, or give it a new password (the old one
    stops working at once). Runs in one transaction with the audit entry."""
    machine = get(db, Machine, machine_id)
    _require_postgres(db)
    username = machine.plc_db_username or username_for(machine.code)
    if not _ROLE_RE.match(username):  # identifiers are interpolated below
        raise AppError("INVALID_PLC_USERNAME", "Nombre de usuario PLC no válido.", 422)
    taken = (
        db.query(Machine)
        .filter(Machine.plc_db_username == username, Machine.id != machine.id)
        .first()
    )
    if taken is not None:
        raise AppError(
            "PLC_USERNAME_TAKEN",
            f"El usuario {username} ya pertenece a la máquina {taken.code}.",
            409,
        )
    settings = get_settings()
    password = _new_password()
    created = machine.plc_db_username is None
    verb = "ALTER" if _role_exists(db, username) else "CREATE"
    db.execute(
        text(
            f'{verb} ROLE "{username}" WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE '
            f"INHERIT CONNECTION LIMIT {CONNECTION_LIMIT} PASSWORD '{password}'"
        )
    )
    db.execute(text(f'GRANT {GROUP_ROLE} TO "{username}"'))
    db.execute(text(f"ALTER ROLE \"{username}\" SET statement_timeout = '{STATEMENT_TIMEOUT}'"))
    # PLC timestamps without an offset are local time (NFR-7a).
    tz = settings.tz.replace("'", "")
    db.execute(text(f"ALTER ROLE \"{username}\" SET timezone = '{tz}'"))
    machine.plc_db_username = username
    db.flush()
    audit_service.record(
        db, user=actor, entity="machine", entity_id=machine.id,
        action="plc_credentials_create" if created else "plc_credentials_rotate",
        before={"code": machine.code, "plc_db_username": None if created else username},
        after={"code": machine.code, "plc_db_username": username},
    )
    database = db.execute(text("SELECT current_database()")).scalar_one()
    db.commit()
    db.refresh(machine)
    return PlcCredentials(
        machine=machine, username=username, password=password, created=created,
        host=settings.plc_db_host, port=settings.plc_db_port, database=database,
    )
