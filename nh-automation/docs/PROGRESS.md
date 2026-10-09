# Progress

## Phase 0 — Foundation (2026-10-08)

### What was built

- **Repo layout** per `00-overview.md` §3: `backend/`, `frontend/`, `deploy/`, `tools/` (empty, reserved for phase 4+), `docs/`.
- **Backend** (FastAPI + SQLAlchemy 2 + Alembic + PostgreSQL):
  - Tables: `users`, `audit_log`, `settings`, plus a `sessions` table for
    server-side auth (see `docs/DECISIONS.md`). One migration:
    `backend/migrations/versions/732ef7916919_phase0_foundation.py`.
  - `app/core`: `config.py` (env settings), `timezone.py` (UTC ↔ America/Mazatlan,
    `local_today()`), `security.py` (Argon2 hashing, session/CSRF tokens),
    `permissions.py` (full role→permission map from overview §4),
    `errors.py` (shared `{"error": {...}}` envelope).
  - `app/services`: `auth_service` (password + PIN login, lockout,
    session create/touch/revoke), `user_service` (CRUD, last-master-admin
    protection BR-15), `audit_service` (generic `record`/`list_entries`),
    `settings_service` (defaults + get/update).
  - `app/api/v1`: `health`, `auth` (login, pin-login, logout, me,
    change-password), `users` (CRUD, deactivate/activate, reset-credentials),
    `audit` (read-only list/filter), `settings` (list/update). All
    state-changing endpoints enforce CSRF (double-submit cookie) and
    permission checks via `require_permission`.
  - `app/cli.py`: `create-master-admin`, `seed-settings` (Typer).
  - 43 backend tests (`pytest`): login success/failure, lockout and its
    expiry, PIN login, session expiry, CSRF enforcement, logout, change
    password, full permission matrix (4 roles × 3 permission-gated
    endpoints), user CRUD, last-master-admin protection (deactivate and
    demote), audit entries written on create/update/deactivate, timezone
    helpers (including the 06:30 UTC → previous local day case from the
    spec). All pass; `ruff` and `mypy` are clean.
- **Frontend** (React + TypeScript + Vite + Mantine + TanStack Query):
  - `AuthProvider`/`useAuth`, `RouteGuard` (permission-based route gating),
    `Layout` (top bar with user/role menu + change password/logout,
    permission-filtered side nav).
  - Pages: `LoginPage` (password/PIN tabs), `HomePage` (Inicio placeholder),
    `UsersPage` (list, search, create, edit, deactivate/activate, reset
    credentials), `ChangePasswordPage`, `AuditLogPage` (list + entity
    filter), `SettingsPage` (edit the six default keys), `OperatorStationPage`
    (placeholder; operators are redirected here instead of Inicio).
  - `src/i18n/strings.ts`: single Spanish strings module, no hard-coded text
    in components. `src/utils/datetime.ts`: dd/mm/aaaa, 24h,
    America/Mazatlan, `1,000.00 L` formatting.
  - 7 Vitest tests (datetime helpers incl. the UTC-06:30 case, API client
    error mapping). `npm run build`, `lint`, `typecheck` all clean.
- **Docker / ops**: `deploy/docker-compose.dev.yml` (hot-reload api + web,
  Postgres with a published port for local tools), `deploy/docker-compose.prod.yml`
  (built images, restart policies, health checks, Caddy with internal HTTPS,
  no ports published on `db`), `deploy/Caddyfile`, `deploy/backup.Dockerfile`
  + `backup.sh` + `crontab` (nightly `pg_dump`, gzip, 30-day pruning),
  `deploy/restore.sh`.
- `README.md` (setup + command reference) and the `CLAUDE.md` "Commands"
  section filled in.

### Deviations from the spec

- `sessions` table added (not in `01-data-model.md`) to implement
  "server-side sessions (DB or signed cookie with server check)" — see
  `docs/DECISIONS.md` for the reasoning. Treat it as shared infrastructure,
  not a new business entity.
- `app/db/types.py` adds a `JSONVariant` column type so the Postgres-only
  `JSONB` columns (`audit_log.before/after`, `settings.value`) also work
  against the in-memory SQLite database used by the test suite. Production
  migrations are unaffected (still plain `JSONB`, Postgres only).

### Fixed after initial write-up

- **`pg_isready` healthcheck bug.** Both compose files' `db` healthcheck ran
  `pg_isready -U <user>` with no `-d` flag, which makes `pg_isready` default
  to checking a database named after the *user* (`nh_app`) instead of the
  actual app database (`nh_automation`). Postgres itself was fine, but the
  `db` service never reported healthy, so `api` (which has
  `depends_on: db: condition: service_healthy`) couldn't (re)start on a
  fresh container, surfacing as `database "nh_app" does not exist` with no
  other visible error. Fixed by adding `-d ${POSTGRES_DB}` to the
  `pg_isready` command in both `deploy/docker-compose.dev.yml` and
  `deploy/docker-compose.prod.yml`.

### Verified end-to-end (2026-10-08, after the healthcheck fix)

- `docker compose -f deploy/docker-compose.dev.yml up --build` starts `db`
  (healthy), `api`, `web`.
- Alembic migration `732ef7916919` applied automatically against the real
  Postgres container on `api` startup (confirmed in `api` logs).
- `GET http://localhost:8000/api/v1/health` → `{"status": "ok", "database": "ok"}`.
- `create-master-admin` run interactively in the user's own terminal
  (`docker compose ... exec api python -m app.cli create-master-admin`);
  login at `http://localhost:5173/login` with the resulting account works.

### Known issues / not verified

- **Prod compose stack** (`docker-compose.prod.yml`) and the
  `backup.sh`/`restore.sh` scripts still haven't been exercised against a
  live container — only the dev stack was run. Worth a one-time dry run
  before a real deployment.
- Backend tests run against an in-memory SQLite database (see
  `tests/conftest.py`), not PostgreSQL — the app itself now has been
  confirmed against real Postgres via the dev stack, but the test suite
  itself still uses SQLite for speed.
- No Playwright end-to-end test yet (listed as optional in `00-overview.md` §2).
- `tools/` is still empty; reserved for the phase 4 PLC simulator.

### Definition of done

- [x] `docker compose up` (dev) starts db, api, web; `GET /health` OK — verified end-to-end after the healthcheck fix above.
- [x] `create-master-admin` works; master admin logs in and manages users in Spanish UI — verified end-to-end (CLI run by the user, login confirmed in the browser).
- [x] Operator PIN login works and lands on the operator placeholder — verified via backend tests (login itself); frontend redirect (`IndexRoute` → `/operador`) implemented but not separately click-tested with a real operator account.
- [x] Audit log shows user changes with local timestamps — verified via backend tests (entries written on create/update/deactivate) and frontend datetime formatting tests.
- [ ] Prod compose builds; backup produces a dump; restore script tested once — **not run yet** (see Known issues).
- [x] Lint, type checks and tests pass — backend: `ruff check`, `mypy`, `pytest` (43/43) all clean. Frontend: `eslint`, `tsc --noEmit`, `vitest` (7/7), `npm run build` all clean.
- [x] `CLAUDE.md` "Commands" section filled in.
- [x] `docs/PROGRESS.md` updated (this entry).

## Phase 1 — Catalogs and Inventory (2026-10-09)

### What was built

- **Owner's change:** product/inventory data comes from an **external database
  of unknown structure**, not a spreadsheet. The import is a pluggable pipeline
  (`app/services/imports/`: `sources.py`, `columns.py`, `import_service.py`).
  The `external_db` source runs a configured read-only SELECT (setup guide:
  `backend/external_sources/README.md`, example queries `*.sql.example`), and
  CSV/XLSX upload is kept as a fallback. See `docs/DECISIONS.md`.
- **Backend**
  - Tables `sites`, `clients`, `products`, `packaging_items`, `machines`,
    `stock_levels`, `stock_movements`. Migration
    `b1c4e2a9f301_phase1_catalogs_inventory.py` also seeds the default site,
    NOBELTECH/AGRONB and the 14 packaging items, and sets `default_site_id`.
  - Services: `catalog_service` (CRUD, unique codes, deactivation, one default
    site), `machine_service` (key shown once, SHA-256 stored, rotate),
    `stock_service` (`get_available`, `apply_movement` with row lock + atomic
    increment; reserved = 0 until phase 2), `inventory_service` (stock list
    with filters, receipts, adjustments, movements, alerts), `imports/*`,
    `seed_service`.
  - Endpoints per spec: `/products`, `/packaging-items`, `/clients`, `/sites`,
    `/machines` (+ `rotate-key`), `/imports/{kind}/preview|confirm`
    (+ `/imports/{kind}/sources`), `/inventory`, `/inventory/movements`,
    `/inventory/receipts`, `/inventory/adjustments`, `/inventory/availability`,
    `/inventory/alerts` (+ `/inventory/movement-users`). Every write is audited.
  - CLI: `seed-dev`, `seed-catalogs`, `import-catalog` (preview or `--apply`).
  - New deps: `python-multipart`, `openpyxl` (rebuild the `api` image).
- **Frontend**
  - Catálogos (Productos, Materiales de empaque, Clientes, Sitios, Máquinas)
    on a generic `CatalogPage` (search, active filter, pagination,
    create/edit, activate/deactivate). Machine key dialog with copy button;
    key rotation with confirmation; "Marcar como predeterminado" for sites.
  - Importar dialog (source, mode, file, preview table with error/warning
    highlighting, confirm disabled while there are errors).
  - Inventario: Productos / Materiales de empaque tabs (site, category,
    search, low-stock, negative and inactive filters; the reserved column is
    shown, 0 for now), Movimientos tab (item, type, site, user and local
    date-range filters; order/assignment link when present), Entrada and
    Ajuste dialogs (the adjustment shows current stock and the delta).
  - Inicio: stock alerts card. Top bar: alert count badge.
- **Tests:** backend 128 passing (up from 43), plus a PostgreSQL concurrency
  test that is skipped unless `TEST_POSTGRES_URL` is set (run once and passed). Frontend 12 (up from 7).
- Samples: `tools/samples/productos_ejemplo.csv`, `materiales_ejemplo.csv`.

### Deviations from the spec

- FR-CAT-7 source changed to "external DB (configurable) + CSV/XLSX" at the
  owner's request.
- A single `NUMERIC(12,2)` quantity column for both item kinds (see DECISIONS).
- `default_site_id` setting made read-only (derived from `sites.is_default`).
- Phase-0 model fix: `audit_log.entity` / `user_id` now declare the indexes
  their migration already creates (`alembic check` was reporting drift). No
  new migration was needed.

### Verified end-to-end (dev stack, PostgreSQL)

- Migration `b1c4e2a9f301` applied on `api` start; `alembic check` reports no
  drift; seed counts correct (1 site, 2 clients, 14 packaging items).
- `seed-dev`, then via the API: CSV import (preview → confirm, upsert,
  initial stock), packaging import, inventory list, alerts, adjustment with
  computed delta, movements list; admin is denied `/audit` (403).
- Concurrency test with 20 threads against a scratch PostgreSQL database:
  on hand == sum of movements, a single stock row.
- UI loaded in Chrome (Inicio alerts card + badge, Inventario materiales tab,
  Catálogos → Máquinas) with no console errors.

### Known issues / not verified

- **The external DB source has not run against the real system** (no access
  yet). It was tested with an SQLite file that has a different schema. Pending:
  driver, `.sql` files, and the source-of-truth/sync decision
  (TODO(external-db)).
- UI flows (create/edit forms, import dialog, Entrada/Ajuste dialogs, machine
  key dialog) were exercised through the API and type-checked builds, but
  were not click-tested in the browser.
- Low-stock thresholds of the seeded packaging items are 0 until someone sets them.
- Prod compose, backup and restore are still not exercised (carried over from phase 0).
- Frontend bundle > 500 kB warning (no code splitting yet).

### Definition of done

- [x] All catalogs manageable in Spanish UI; seed data present.
- [x] A sample product spreadsheet imports correctly; errors are shown before
      saving (tests + live run with `tools/samples/productos_ejemplo.csv`). The
      external-DB source follows the same flow (tested with a stand-in DB).
- [x] Receipts and adjustments update stock with movements and audit entries.
- [x] Alerts visible (Inicio card, top-bar badge, inventory badges/filters).
- [x] Tests pass; `docs/PROGRESS.md` updated.
