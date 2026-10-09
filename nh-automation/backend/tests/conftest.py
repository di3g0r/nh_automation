"""Test fixtures.

Uses an in-memory SQLite database (see app/db/types.py for the JSONB/JSON
variant that makes the same models work on both engines). Alembic migrations
target Postgres specifically (the production database per overview §2) and
are exercised separately; these fixtures create the schema directly from the
models so each test gets a clean, fast database.
"""

from __future__ import annotations

import os

os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")
os.environ.setdefault("SECRET_KEY", "test-secret")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_db
from app.core.permissions import Role
from app.core.security import hash_secret
from app.db.base import Base
from app.main import app
from app.models.user import User
from app.services import settings_service

# Importing app.main already pulls in every model transitively (via the API
# routers), which registers them on Base.metadata before create_all() runs.


@pytest.fixture()
def engine():
    eng = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(eng)
    yield eng
    Base.metadata.drop_all(eng)
    eng.dispose()


@pytest.fixture()
def db_session(engine) -> Session:
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = TestingSessionLocal()
    settings_service.ensure_defaults(session)
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def client(engine, db_session):
    def _override_get_db():
        TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def make_user(
    db_session: Session,
    *,
    username: str = "jdoe",
    full_name: str = "Jane Doe",
    role: str = Role.ADMIN.value,
    password: str = "correct-password",
    pin: str | None = None,
    is_active: bool = True,
) -> User:
    user = User(
        username=username,
        full_name=full_name,
        role=role,
        password_hash=hash_secret(password),
        pin_hash=hash_secret(pin) if pin else None,
        is_active=is_active,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def login(client: TestClient, username: str, password: str):
    return client.post("/api/v1/auth/login", json={"username": username, "password": password})


def auth_headers(client: TestClient) -> dict[str, str]:
    """Pull the CSRF cookie set by login into the header the API expects."""
    csrf = client.cookies.get("nh_csrf")
    return {"X-CSRF-Token": csrf} if csrf else {}


@pytest.fixture()
def base_catalogs(db_session):
    """Production seed (data model §5): default site, 2 clients, 14 packaging items."""
    from app.services import seed_service

    return seed_service.ensure_base_catalogs(db_session)


def login_as(client: TestClient, db_session: Session, role: str) -> dict[str, str]:
    """Create a user with `role`, log in, and return the CSRF headers."""
    username = f"user_{role}"
    if db_session.query(User).filter(User.username == username).first() is None:
        make_user(db_session, username=username, role=role, password="pw-1234567")
    login(client, username, "pw-1234567")
    return auth_headers(client)
