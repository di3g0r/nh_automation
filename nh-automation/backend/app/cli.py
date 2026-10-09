"""Operational CLI. Run inside the API container, e.g.:

    docker compose -f deploy/docker-compose.dev.yml exec api \
        python -m app.cli create-master-admin
"""

from __future__ import annotations

import getpass

import typer

from app.core.permissions import Role
from app.core.security import hash_secret
from app.db.session import SessionLocal
from app.models.user import User
from app.services import seed_service, settings_service
from app.services.user_service import get_by_username

cli = typer.Typer(add_completion=False)


@cli.command("create-master-admin")
def create_master_admin(
    username: str = typer.Option(..., prompt=True),
    full_name: str = typer.Option(..., prompt="Full name"),
    password: str = typer.Option(
        None, prompt="Password", confirmation_prompt=True, hide_input=True
    ),
) -> None:
    """Create the first master admin (FR-AUTH-6). Idempotent: a username that
    already exists is reported, not overwritten."""
    db = SessionLocal()
    try:
        if get_by_username(db, username) is not None:
            typer.echo(f"El usuario '{username}' ya existe. No se creó nada.")
            raise typer.Exit(code=1)

        if not password:
            password = getpass.getpass("Password: ")

        user = User(
            username=username,
            full_name=full_name,
            role=Role.MASTER_ADMIN.value,
            password_hash=hash_secret(password),
            is_active=True,
        )
        db.add(user)
        db.commit()
        settings_service.ensure_defaults(db)
        typer.echo(f"Administrador maestro '{username}' creado correctamente.")
    finally:
        db.close()


@cli.command("seed-settings")
def seed_settings() -> None:
    """Ensure all default settings keys exist (safe to run repeatedly)."""
    db = SessionLocal()
    try:
        settings_service.ensure_defaults(db)
        typer.echo("Configuración por defecto asegurada.")
    finally:
        db.close()


@cli.command("seed-catalogs")
def seed_catalogs() -> None:
    """Ensure the base site, clients and 14 packaging items exist (idempotent).
    The phase-1 migration already inserts them; this is for repaired/old DBs."""
    db = SessionLocal()
    try:
        seed_service.ensure_base_catalogs(db)
        typer.echo("Catálogos base asegurados.")
    finally:
        db.close()


@cli.command("seed-dev")
def seed_dev() -> None:
    """DEV ONLY: sample products, machines M01-M06 and one user per role."""
    from app.core.config import get_settings

    if get_settings().is_production:
        typer.echo("seed-dev no se puede ejecutar en producción.")
        raise typer.Exit(code=1)
    db = SessionLocal()
    try:
        created = seed_service.seed_dev(db)
        typer.echo("Creado: " + (", ".join(created) if created else "nada (ya existía)."))
        typer.echo(
            f"Usuarios dev: contraseña '{seed_service.DEV_PASSWORD}', "
            f"PIN de operador '{seed_service.DEV_PIN}'."
        )
    finally:
        db.close()


@cli.command("import-catalog")
def import_catalog(
    kind: str = typer.Argument(..., help="products | packaging-items"),
    source: str = typer.Option("external_db", help="external_db | file"),
    file: str = typer.Option(None, help="Ruta del archivo CSV/XLSX (source=file)"),
    mode: str = typer.Option("create_only", help="create_only | upsert"),
    apply: bool = typer.Option(False, "--apply", help="Guardar (sin esto solo vista previa)"),
    username: str = typer.Option(None, help="Usuario registrado en la bitácora (--apply)"),
) -> None:
    """Preview (default) or apply a catalog import from the command line."""
    from pathlib import Path

    from app.core.errors import AppError
    from app.services.imports import import_service
    from app.services.imports.sources import SourceInput

    if kind not in ("products", "packaging-items"):
        typer.echo("kind debe ser 'products' o 'packaging-items'.")
        raise typer.Exit(code=2)
    data = SourceInput()
    if file:
        path = Path(file)
        data = SourceInput(filename=path.name, content=path.read_bytes())

    db = SessionLocal()
    try:
        if apply:
            actor = get_by_username(db, username) if username else None
            if actor is None:
                typer.echo("--apply requiere --username de un usuario existente.")
                raise typer.Exit(code=2)
            result = import_service.confirm(
                db, kind, source=source, mode=mode, data=data, actor=actor  # type: ignore[arg-type]
            )
        else:
            result = import_service.preview(db, kind, source=source, mode=mode, data=data)  # type: ignore[arg-type]
    except AppError as exc:
        typer.echo(f"Error: {exc.message} {exc.details or ''}")
        raise typer.Exit(code=1) from exc
    finally:
        db.close()

    typer.echo(f"Columnas reconocidas: {result.columns}")
    if result.unknown_columns:
        typer.echo(f"Columnas ignoradas: {result.unknown_columns}")
    for err in result.global_errors:
        typer.echo(f"ERROR: {err}")
    for row in result.rows:
        if row.errors or row.warnings:
            notes = "; ".join(row.errors + row.warnings)
            typer.echo(f"Fila {row.row_number} [{row.action}]: {notes}")
    typer.echo(f"Resumen: {result.summary}" + (" (guardado)" if apply else " (vista previa)"))


if __name__ == "__main__":
    cli()
