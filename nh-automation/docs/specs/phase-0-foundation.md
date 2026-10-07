# Phase 0 — Foundation

> Prerequisites: none. Read `00-overview.md` and `01-data-model.md` first.
> Goal: a running skeleton where the master admin can log in and manage users.

## Scope

**In:** repository layout, Docker Compose (dev + prod), PostgreSQL, Alembic, FastAPI app skeleton, React app skeleton with Spanish UI shell, authentication, roles/permissions, user CRUD, audit log, settings, health check, backups, README.
**Out:** catalogs, inventory, orders (later phases).

## Tables

`users`, `audit_log`, `settings` (see `01-data-model.md`).

## Requirements

### Infrastructure
- **P0-1** Repo structure as in overview §3. `.gitignore`, `.env.example`, `README.md`.
- **P0-2** `docker-compose.dev.yml`: `db`, `api` (hot reload), `web` (Vite dev server or Caddy). `docker compose -f deploy/docker-compose.dev.yml up` starts everything.
- **P0-3** `docker-compose.prod.yml`: `db`, `api`, `web` (Caddy with built frontend, internal HTTPS), `backup`. Restart policies and health checks.
- **P0-4** API runs Alembic migrations on start.
- **P0-5** `backup` service: nightly `pg_dump` to a mounted folder, deletes dumps older than 30 days. `deploy/restore.sh` restores a dump.
- **P0-6** `TZ=America/Mazatlan` configured; backend has helpers to convert UTC ↔ local and to get "today" in local time.

### Authentication (FR-AUTH)
- **FR-AUTH-1** Login with username + password.
- **FR-AUTH-2** Operator login with username + PIN (4–6 digits).
- **FR-AUTH-3** Server-side sessions (DB or signed cookie with server check); inactivity timeout 8 h office, 12 h operator (settings).
- **FR-AUTH-4** Lock account 15 min after 5 failed attempts.
- **FR-AUTH-5** Change own password/PIN; master admin resets anyone's.
- **FR-AUTH-6** CLI command `create-master-admin` for first deployment.
- CSRF protection for state-changing requests.

### Permissions
- Role → permission map in one module (overview §4). Dependency/decorator `require_permission("users.manage")` used on endpoints.

### Users (FR-USR)
- **FR-USR-1** Fields: username, full name, role, active, password, optional PIN.
- **FR-USR-2** Deactivate instead of delete; deactivated users cannot log in.
- **FR-USR-3** Cannot deactivate or demote the last active master admin (BR-15).

### Audit log (FR-AUD)
- Generic service `audit.record(user, entity, entity_id, action, before, after)` used by all later phases.
- **FR-AUD-2** Master admin can list/filter it (user, entity, date range); no edit/delete.

### Settings
- Key/value store with defaults in code: `default_site_id`, `approver_must_differ` (false), `plc_offline_seconds` (60), `session_timeout_office_hours` (8), `session_timeout_operator_hours` (12), `difference_tolerance_liters` (0).
- Master admin can view/edit.

### API endpoints
`POST /auth/login`, `POST /auth/pin-login`, `POST /auth/logout`, `GET /auth/me`, `POST /auth/change-password`; `GET/POST /users`, `GET/PATCH /users/{id}`, `POST /users/{id}/deactivate`, `POST /users/{id}/activate`, `POST /users/{id}/reset-credentials`; `GET /audit`; `GET/PATCH /settings`; `GET /health`.

### Frontend
- App shell: top bar (user name, role, logout), side navigation per overview §6 (later items can be placeholders hidden until their phase).
- Screens: **Iniciar sesión** (password and PIN modes), **Usuarios** (list, search, create, edit, deactivate, reset), **Cambiar contraseña**, **Bitácora**, **Configuración**, empty **Inicio**.
- Spanish strings module; date/time formatting helpers in America/Mazatlan.
- Route guards by permission; operators redirected to a placeholder **Estación de operador**.

## Tests
- Login success/failure, lockout, session expiry, PIN login.
- Permission checks: each role on each endpoint (allowed vs 403).
- Last master admin protection.
- Audit entries written for user create/update/deactivate.
- Time zone helper: a UTC timestamp at 06:30 UTC is the previous local day.

## Definition of done
- [ ] `docker compose up` (dev) starts db, api, web; `GET /health` OK.
- [ ] `create-master-admin` works; master admin logs in and manages users in Spanish UI.
- [ ] Operator PIN login works and lands on the operator placeholder.
- [ ] Audit log shows user changes with local timestamps.
- [ ] Prod compose builds; backup produces a dump; restore script tested once.
- [ ] Lint, type checks and tests pass. `CLAUDE.md` "Commands" section filled in. `docs/PROGRESS.md` updated.
