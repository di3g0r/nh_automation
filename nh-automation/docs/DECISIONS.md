# Decisions

Record decisions made during implementation that are not in the specs (date, decision, reason).

## 2026-10-08 — Phase 0

- **Server-side session storage.** Added a `sessions` table (not listed in
  `01-data-model.md`, which only requires "server-side sessions (DB or signed
  cookie with server check)" for FR-AUTH-3). It is infrastructure, not a
  business entity, so it doesn't change the shared data model. Columns:
  `user_id`, `token_hash` (SHA-256 of the random session token, not the token
  itself), `csrf_token`, `user_agent`, `expires_at`, `last_seen_at`,
  `revoked_at`. The session cookie is httpOnly; a separate non-httpOnly
  cookie carries the CSRF token for the double-submit pattern required by
  overview §5.
- **CSRF: double-submit cookie.** `nh_csrf` cookie (readable by frontend JS)
  must match the `X-CSRF-Token` header on every state-changing request
  (`POST`/`PATCH`/`PUT`/`DELETE`). Enforced in `app/api/deps.py:get_current_user`.
- **`create-master-admin` as a Typer CLI** (FR-AUTH-6), run via
  `docker compose ... exec api python -m app.cli create-master-admin`.
  Idempotent: refuses to run if the username already exists.
- **Lockout counter shared between password and PIN login.** `01-data-model.md`
  defines one `failed_attempts`/`locked_until` pair per user; a wrong PIN and
  a wrong password count against the same 5-attempt/15-minute lockout
  (FR-AUTH-4). Simplest reading that still protects both login paths.
- **Settings values are heterogeneous JSON**, not nested objects (a bool, an
  int, or `null`), matching the six default keys in `phase-0-foundation.md`
  "Settings". `app/db/types.py` defines a `JSONVariant` (Postgres `JSONB` in
  prod, `JSON` under SQLite) so the same models back both the production
  database and the fast in-memory test database -- Alembic migrations still
  target Postgres only, per the stack choice in `00-overview.md` §2.
- **Full permission map defined now, only partly enforced.** `00-overview.md`
  §4 says the role→permission map lives in one shared module; `app/core/permissions.py`
  defines all permissions from the table, but phase 0 only wires
  `users.manage`, `audit.view`, `settings.manage` to actual endpoints (the
  others have no routes yet). TODO markers are unnecessary here since the
  later phases simply add routes that import the existing map.
