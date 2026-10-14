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

## Phase 2 — Work orders and reservations (2026-10-13)

Built across two sessions: the first one stopped unexpectedly after the
backend and the list/form pages were written; the second one finished the UI,
verified everything and wrote these notes.

### What was built

- **Data model** (migration `d4e8a1b2c3f5`): `work_orders`,
  `order_base_products`, `order_packaging`, `order_checklist` (4 rows per
  order), `order_comments`, `reservations`; FK `stock_movements.order_id` →
  `work_orders`.
- **Services:** `order_service` (create/edit/delete/cancel, comments,
  history, list with filters, print data, snapshots FR-ORD-1, numbering
  BR-19, rework BR-20/21, razón social BR-22) and `reservation_service`
  (reserve/release with row locking, overselling block BR-2/3, packaging
  warnings BR-4). `stock_service` now returns real reserved/available; a
  razón social code used by an order can no longer be changed.
- **API:** `GET/POST /orders`, `GET/PATCH/DELETE /orders/{id}`,
  `POST /orders/{id}/cancel`, `GET/POST /orders/{id}/comments`,
  `GET /orders/{id}/history`, `GET /orders/{id}/print-data`,
  `GET /inventory/availability` (`exclude_order_id`),
  `GET /inventory/reservations`.
- **Frontend:** Órdenes list (status/type badges, all FR-ORD-2 filters,
  search); Nueva/Editar orden form following the paper form (Retrabajo
  checkbox, rework kind, related order, live availability per base product,
  automatic/required razón social, packaging availability); Detalle de orden
  with tabs Información / Materiales / Checklist (read-only) / Comentarios /
  Historial and actions Editar / Imprimir / Cancelar (reason) / Eliminar by
  status and permission; Imprimir page (letter size, Code 128 barcodes);
  inventory *Reservado* opens the orders holding the reservation.
- **Tests:** backend 211 passed + 5 skipped (4 Postgres-only concurrency
  tests, 1 pre-existing); `tests/test_orders.py` covers every test in the
  spec and acceptance scenarios 1–7. Frontend 20 (new `formatHistoryValue`).

### Verified end-to-end

- Concurrency tests (`tests/test_orders_concurrency.py`) run inside the `api`
  container against a scratch PostgreSQL database: 4 passed (last liters,
  distinct numbers, opposite lock order without deadlock, concurrent edits).
- `alembic check` on the dev stack: no drift.
- Acceptance scenarios on an isolated scratch database (the dev database was
  not touched): 1 created through the UI → `T-1 ANB`, *Pendiente* expiry,
  1,000 L reserved / 500 L available; 2 blocked with the exact spec message
  naming `T-1 ANB`; 3 mixed NB+ANB requires a choice, NB → `T-2 NB`;
  4 own-stock rework → `R-1 NB`, no client, edit form has no type switch and
  PATCH of `order_type` is refused; 5 Production manager edits twice + comment,
  shown with author and time in Comentarios and Historial; 6 packaging warning
  shown in the form, on save and on the detail page; 7 print page lists both
  base products, the type badge and both barcodes. Cancel via the UI modal
  releases stock and shows reason/author. No console errors.

### Deviations from the spec

- None in behavior. Small additions: `GET /inventory/reservations` (for the
  reserved drill-down) and `exclude_order_id` on availability (for editing).

### Known issues / not verified

- Not click-tested: delete through the UI and the related-order picker
  (Retrabajo de orden anterior). Both are covered by API tests, but phase 2
  cannot produce a completed order, so the picker is always empty for now.
- The print page was checked on screen, not on paper; page breaks on long
  orders are untested.
- One full backend run (out of five) failed 7 tests with an argon2 hashing
  error, likely transient memory pressure on the dev machine; the same tests
  pass in isolation and the four later full runs were clean. Not reproduced,
  so not fixed. If it recurs, look at the argon2 memory cost used by
  `hash_secret` in tests.
- Carried over: README still mentions Caddy proxying `/plc`; prod compose /
  backup / restore not exercised; bundle > 500 kB.

### Definition of done

- [x] Scenarios pass manually and in automated tests.
- [x] Audit log records create/edit/cancel/delete/comment
  (`test_audit_log_records_every_order_action`).
- [x] Tests pass; `docs/PROGRESS.md` updated.

## Phase 3 — Production manager, machines, production controls, closing (2026-10-13)

### What was built

- **Operators leave the platform (v3.1).** Permission map has three roles (admin
  lost `production.control`; legacy `operator` has none). Login refuses
  operators with *"Los operadores no usan la plataforma."* (only with the right
  password); existing operator sessions get 401. `/auth/pin-login` and every PIN
  field are gone (the `pin_hash` column stays). The API rejects role `operator` on
  create and edit. `seed-dev` creates no operator. Operator station page,
  landing rule and PIN tab removed.
- **Migration `e6f1a3b5c7d9`:** `assignments`, `assignment_events`, FK
  `stock_movements.assignment_id`. It also deactivates operator users (audited
  `via: migration:phase3`), revokes their sessions and deletes the
  `session_timeout_operator_hours` setting.
- **`assignment_service`:** replaces the whole split (BR-7, exact sum), queue and
  reorder (BR-14), start/pause/resume/complete with an `Actor` (manual user or,
  from phase 4, `Actor.plc(machine)`), derived order status (§3) and completion
  stock (BR-8/9/10). Base consumption is computed on the cumulative actual liters,
  so 2-decimal rounding never loses liters. Packaging is consumed when the order
  completes; corrections before closing write only the difference.
- **`order_service`:** expiry (BR-20). Editing is also allowed in `assigned`, and
  changing products or liters deletes the split (BR-16). Cancelling also cancels
  the assignments. Adds checklist, lots and materials (BR-24), closing (BR-11),
  and new fields in `OrderOut`: assignments, difference, flags, `close_missing`
  and who/when. The print data includes who assigned.
- **`production_service`:** read models for Por asignar / En producción / Por
  cerrar, the machine board and machine queues.
- **API:** every endpoint listed in the spec (`app/api/v1/production.py`,
  registered before catalogs so `/machines/board` works).
- **Frontend:** Producción page (10 s refresh); expiry, assign-machines and close
  modals; production buttons with a Terminar confirmation. Order detail has a
  Máquinas tab and editable Checklist (with lots) and Materiales (prefilled with
  planned values), plus history labels for the new actions. Máquinas board (5 s
  refresh, maintenance switch, queue modal with reorder). Inicio summary (today's
  orders by status, machines by state). The print page shows machines, results
  and the close note. **Máquinas** added to the nav.

### Tests

- Backend: **232 passed**, 5 skipped. New: `tests/test_production.py` (38 tests)
  covers every item in the spec's Tests list and scenarios 1–7 at API level.
  Existing auth, permission, user and order tests were updated for three roles.
  `ruff` and `mypy` are clean.
- Postgres concurrency tests (scratch DB): 6 passed.
- Frontend: 26 tests passed (new `utils/production.test.ts`). Lint, typecheck and
  build pass (only the old AuthContext fast-refresh warning remains).

### Verified on PostgreSQL (scratch DB `nh_phase3`; the dev DB was not touched)

- `alembic upgrade head` with a planted operator user and session: the user was
  deactivated and audited, and the session revoked. `downgrade -1` + `upgrade
  head` round trip OK; `alembic check` shows no drift.
- Browser (local API :8001 + Vite :5174 against the scratch DB): the login page
  has no PIN tab; `jefe` lands on Producción, and T-1 ANB shows *Falta fecha de
  caducidad* / *Falta asignar máquinas*. The expiry modal opens.

### Known issues / not verified

- **The click-through stopped at the expiry modal** (usage limit). Typing into
  the Mantine month Select and pressing Enter did not select a value. This may be
  automation-only, but check the picker by hand. Not click-tested: saving expiry,
  the assign modal, production buttons, Terminar, closing, the board/queue modal,
  editable Checklist/Materiales, the print page and Inicio. All of these are
  covered by API tests.
- **The dev DB is not migrated yet:** restart `api` (or run `alembic upgrade
  head`). This deactivates the dev `operador` user, as intended.
- Scratch DB `nh_phase3` is left in the dev Postgres; drop it when done.
- Carried over: prod compose / backup / restore not exercised; bundle > 500 kB.

### Definition of done

- [x] The whole paper process can be done in the system without PLCs (API +
      UI built; UI only partly click-tested, see above).
- [~] Scenarios pass in automated tests; manual run incomplete.
- [x] Tests pass; `docs/PROGRESS.md` updated.
