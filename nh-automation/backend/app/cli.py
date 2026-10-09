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
from app.services import settings_service
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


if __name__ == "__main__":
    cli()
