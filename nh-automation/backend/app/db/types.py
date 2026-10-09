"""Shared column types.

JSONVariant is Postgres JSONB in production, and plain JSON on SQLite -- used
only by the test suite (see tests/conftest.py) so the same models work
against both without touching the Alembic migrations, which target Postgres
only, per the stack choice in overview §2.
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

JSONVariant = JSONB().with_variant(sa.JSON(), "sqlite")
