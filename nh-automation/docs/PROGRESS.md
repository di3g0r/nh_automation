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

## Phase 1b — v2/v3 updates (2026-10-13)

### What was built

- **Roles and permissions.** `supervisor` → `production_manager` (*Jefe de
  producción*) everywhere. `app/core/permissions.py` matches overview §4
  exactly (added `sequences.manage`, `orders.comment`, `orders.expiry`,
  `orders.close`, `production.control`, `machines.plc_credentials`; removed
  `orders.approve`, `orders.verify`, `assignments.work_own`). `inventory.move`
  is master admin + admin only; the Production manager views inventory and
  catalogs but cannot move stock or edit catalogs.
- **Migration `c7d2f4a8b913_phase1b_v2_updates`:** converts supervisor users,
  adds `ck_users_role`; creates and seeds `razones_sociales` (NB, ANB, RS3,
  RS4 — `TODO(OPEN-16)`) and `order_sequences` (T/R, next 1); adds
  `products.razon_social_id` (FK, nullable, indexed); deactivates the
  NOBELTECH/AGRONB clients (audited); deletes `approver_must_differ`; adds
  `difference_tolerance_percent` (`TODO(OPEN-19)`). Downgrade reverses it.
- **Backend:** razón social CRUD (`/razones-sociales`, audited, code 1–6
  uppercase letters/digits, unique); `/order-sequences` (GET/PATCH,
  `sequences.manage`, audited) in `sequence_service`; products require an
  active razón social on create, reject clearing it on edit, return
  `razon_social_code/name`, and filter by `razon_social_id` /
  `without_razon_social`; import column `razon_social` (+ aliases) with
  error/warning/no-clear rules; tolerance validation in `settings_service`.
  `seed-catalogs` = site + razones sociales + sequences + packaging (no
  clients); `seed-dev` adds `jefe`, two fake clients, NB/ANB on the dev
  products (also back-fills existing ones).
- **Frontend:** role label *Jefe de producción*; **Producción** placeholder page
  and nav item; the Production manager lands there after login; Catálogos →
  **Razones sociales**; products show a razón social column (badge *Sin razón
  social*), a filter (including "Sin razón social") and a required select in
  the form; Configuración shows *Tolerancia de diferencia (L)* / *(%)* with
  limits and a **Numeración de órdenes** section (master admin) with the
  required warning.
- Samples/docs: `tools/samples/productos_ejemplo.csv` and
  `products.sql.example` include `razon_social`; `external_sources/README.md`
  documents it; README gets a "Network access" (LAN only, no VPN) section;
  README/CLAUDE.md command tables updated. No VPN references existed in code or
  deploy files.
- **Tests:** backend 169 passed + 1 skipped (Postgres-only): new
  `tests/test_phase1b.py` and a rewritten `tests/test_permissions.py` (the map
  is compared against a literal copy of the §4 table, plus every role on every
  gated endpoint). Frontend 13 (new `landing.test.ts`).

### Deviations from the spec

- Added a DB CHECK constraint on `users.role` (the spec mentions
  "enum/check constraint"; there was none before). See DECISIONS.
- The role-migration test runs the migration's `convert_roles` SQL against a
  scratch SQLite table (the suite doesn't run Alembic); the full migration was
  verified on the dev PostgreSQL instead (below).

### Verified end-to-end (dev stack, PostgreSQL)

- Planted a `supervisor` user, ran `alembic upgrade head`: both it and the
  phase-1 dev user `bodega` became `production_manager`; clients NB/ANB
  inactive with audit rows; settings and seeds as expected. Setting a user
  back to `supervisor` is rejected by `ck_users_role`. `alembic downgrade -1`
  + `upgrade head` round trip OK; `alembic check`: no drift.
- `seed-dev` and `seed-catalogs` run cleanly on the migrated DB.
- Browser: `jefe` logs in and lands on Producción (nav: Inicio, Producción,
  Órdenes, Inventario); the master admin sees Razones sociales, the products
  column/badge, both tolerances and Numeración de órdenes in Configuración.
- `import-catalog products --file tools/samples/productos_ejemplo.csv --mode
  upsert --apply` set ANB on the product that had none.

### Known issues / not verified

- The first migration attempt failed (wrong `audit_log` columns) and rolled
  back cleanly; fixed before the successful run.
- Changing a razón social code already used by an order is not blocked yet
  (phase 2).
- Not click-tested: creating/editing a razón social or product through the
  forms, and saving a sequence number from the UI (covered by API tests).
- The `Órdenes` nav item still has no page (phase 2); `Máquinas` (overview §6)
  is not in the nav yet (no page until a later phase).
- README still says Caddy proxies `/plc` (from the obsolete PLC HTTP API
  design); untouched in this phase.
- Carried over: prod compose / backup / restore not exercised; bundle > 500 kB.

### Definition of done

- [x] Migrations apply on the dev stack; `alembic check` shows no drift.
- [x] A *Jefe de producción* user can log in and lands on the Producción placeholder.
- [x] Razones sociales visible and editable in Spanish UI; products show their razón social.
- [x] Sequences visible and editable by the master admin in Configuración.
- [x] Sample CSV with a `razon_social` column imports correctly.
- [x] NOBELTECH/AGRONB no longer active as clients.
- [x] All tests, lint and type checks pass; `docs/PROGRESS.md` updated.
