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

## 2026-10-09 — Phase 1

- **Catalog source is an external database, not a spreadsheet (owner's change
  to FR-CAT-7).** The products/inventory live in a database whose structure is
  unknown. The import is built as a source-agnostic pipeline
  (`app/services/imports/`): *source → column aliasing → per-row validation →
  preview → confirm*. Sources implement the `ImportSource` protocol:
  - `external_db`: any SQLAlchemy URL (`EXTERNAL_CATALOG_DB_URL`) and one
    admin-written, read-only `SELECT` per catalog in
    `backend/external_sources/*.sql`, aliased to canonical column names. The
    query is checked to start with SELECT/WITH, and the transaction is always
    rolled back. Adapting to the real schema means writing SQL and adding the
    driver; no code change in the usual case.
  - `file` (CSV/XLSX): kept as a manual fallback and as a test fixture.
  - TODO(external-db): once access exists, add the DB driver, write the two
    `.sql` files, and decide whether the external DB stays the source of truth
    (an ongoing sync, a future change) or this is a one-time migration (current
    design: a repeatable manual import with "create or update" mode).
- **Confirm re-reads the source** instead of trusting rows sent back by the
  browser. The same validation runs again; any error → 422, nothing saved
  (single transaction).
- **Import modes:** `create_only` skips existing codes (as a warning, not an
  error, so the import can be re-run); `upsert` updates existing codes with the
  **non-empty** source values only (empty cells never clear data) and never
  changes `is_active`.
- **Initial stock on import** is written as a `receipt` "Importación inicial"
  at the default site, **only for items with no movements at that site yet**,
  so re-running an import never doubles stock. Otherwise the row gets a
  warning. Stock per external warehouse is not mapped (single default site);
  add a site column later if the external DB has several warehouses.
- **Packaging category is required on import.** No guessing from code
  prefixes; the external SQL can compute it with a CASE expression (see
  `packaging_items.sql.example`).
- **`stock_levels.on_hand` / `stock_movements.quantity` are `NUMERIC(12,2)` for
  both item kinds** (data model §1 says packaging units are INTEGER). Packaging
  quantities are enforced as whole numbers in
  `stock_service.normalize_quantity`. One column keeps the item xor and
  locking logic in one place.
- **`apply_movement` = row lock + atomic SQL increment.** `SELECT … FOR UPDATE`
  on the stock row (BR-3) plus `UPDATE … SET on_hand = on_hand + :q`, so totals
  stay right even on engines that ignore FOR UPDATE (the SQLite test DB). A race
  to create the stock row is handled with a savepoint and a re-select. It never
  commits: later phases compose it into their own transaction. Verified with
  20 concurrent writers on real PostgreSQL.
- **`stock_movements.order_id` / `assignment_id` are plain integers for now**;
  phases 2 and 3 add the foreign keys when those tables exist.
- **Adjustments:** counted quantity ≥ 0, reason mandatory; a count equal to the
  current on hand is rejected (`ADJUSTMENT_NO_CHANGE`) rather than writing a
  zero movement.
- **Inactive items/sites (FR-CAT-6)** cannot be used in new receipts,
  adjustments or machines. They stay readable and show in old records. There
  are no DELETE endpoints for catalogs.
- **Default site:** the first site becomes the default; exactly one default
  is kept (setting a new default unsets the old one; the default can't be
  deactivated or un-defaulted). The phase-0 `default_site_id` setting is kept
  in sync automatically and is now read-only in Configuración.
- **Catalog reads** need `catalogs.manage` **or** `inventory.view` (the
  supervisor needs item lists for receipts). *(Phase 1b: the supervisor role no
  longer exists; the rule is kept for the Production manager, who views stock
  and will pick products in orders.)* Writes need `catalogs.manage`.
  The Catálogos menu is only shown with `catalogs.manage`.
- **Machine API key:** `nhm_` + 32 random bytes, stored as SHA-256 (high
  entropy, so a slow hash isn't needed, the same as session tokens). Never
  written to the audit log. Dev-seeded machines get random keys that nobody
  sees; rotate from the UI to get one.
- **Low stock** = active packaging, active site, available **strictly below**
  the threshold. The seeded threshold is 0 (unknown), so there are no alerts
  until thresholds are set. **Negative stock** = any item, any site,
  on hand < 0.
- **Production seed lives in the migration** (site, NB/ANB, 14 packaging
  items), frozen inline; `seed-catalogs` is the idempotent equivalent;
  `seed-dev` holds dev-only data and refuses to run in production.
- **`GET /inventory/movement-users`** (not in the spec) feeds the movements
  "user" filter for supervisors, who can't read `/users`.

## 2026-10-13 — Phase 1b

- **Role CHECK constraint.** `users.role` was a free string validated only by
  the schemas. The phase-1b migration converts `supervisor` users to
  `production_manager` and then adds `ck_users_role` (the four v3 roles), so
  the database itself rejects `supervisor`. Adding a role now needs a
  migration.
- **Razón social code normalization.** Codes are uppercased before validation
  (`nb` → `NB`), then must match `^[A-Z0-9]{1,6}$`. Same for import values.
  Names are not required to be unique (the spec only asks for unique codes).
- **Catalog reads include razones sociales** with the same rule as other
  catalogs (`catalogs.manage` or `inventory.view`); writes need
  `catalogs.manage`.
- **Product razón social on edit.** `razon_social_id` is required on create.
  On PATCH, omitting it keeps the current value, and an explicit `null` is
  rejected (`RAZON_SOCIAL_REQUIRED`). The active check only runs when the value
  changes, so a product whose razón social was later deactivated can still be
  edited. The Spanish form always sends it (required select).
- **Import:** `razon_social` holds the code. Unknown **or inactive** code → row
  error. Empty → warning only when the product would end up without one (new
  product, or an existing product that has none); in upsert mode empty never
  clears the stored value. Aliases: `razon_social`, `razón social`, `rs`,
  `empresa`.
- **Client seed correction.** The migration deactivates clients with codes
  `NB`/`ANB` and writes `audit_log` rows with `user_id` NULL and
  `"via": "migration:phase1b"`. Dev sample clients are `DEV1`/`DEV2`
  ("Cliente de prueba … (dev)").
- **Order sequences** live in `order_sequences` with CHECKs (`next_number >= 1`,
  type in trabajo/retrabajo). `PATCH /order-sequences/{order_type}` locks the
  row (`FOR UPDATE`) and audits `entity="order_sequence"`. A lower number is
  allowed (the spec only requires >= 1); the phase-2 unique `operation_number`
  must refuse a collision.
- **Tolerance settings** are JSON numbers validated in `settings_service`:
  liters >= 0, percent 0–100, both at most 2 decimals; integral values are
  stored as ints. Other settings keep the phase-0 behavior (no validation).
  `approver_must_differ` is deleted by the migration and removed from defaults.
- **Production manager landing / nav.** `Producción` is gated by
  `orders.assign` (master admin and Production manager). Landing is decided on
  login (`utils/landing.ts`); `Inicio` stays reachable for the Production
  manager (only operators are always redirected away from it).
- **Dev seed user** for the new role is `jefe`. Existing dev databases keep the
  old `bodega` user, now converted to `production_manager` by the migration.

## 2026-10-13 — Phase 2

- **Reservation locking (BR-3).** `reservation_service.reserve_for_order` locks
  the `stock_levels` rows of the order's base products in stock-row id order,
  then re-reads other orders' active reservations, so concurrent creates/edits
  cannot over-reserve and opposite row orders cannot deadlock. Verified with
  the Postgres-only tests in `tests/test_orders_concurrency.py`.
- **Missing stock row = 0 on hand.** A base product with no `stock_levels` row
  at the order's site is always short; reserving never creates stock rows.
- **One transaction per write.** Every order write commits once at the end; a
  refused create (shortage, validation) consumes no operation number.
- **Edit = release + re-reserve, only for what changed.** Reservations are
  recomputed per item kind; a packaging-only edit does not re-check base
  products. The form's live *Disponible* excludes the order's own
  reservations (`GET /inventory/availability?exclude_order_id=`).
- **Comment on edit.** The optional comment in the edit form is stored as a
  new `order_comments` entry (append-only); if nothing else changed, the
  history shows only a *Comentario* entry, not an *Edición*.
- **Razón social code locked once used.** Changing the code of a razón social
  that already appears in an order is refused (`RAZON_SOCIAL_IN_USE`, 409),
  since the code is part of the operation number (BR-19). Phase-1b TODO.
- **UI permission checks.** `can_edit` / `can_cancel` / `can_delete` in the
  order payload reflect status only; the UI also checks `orders.edit` /
  `orders.cancel`, and the API enforces both.
- **Print view** is a route outside the app shell (`/ordenes/:id/imprimir`)
  with plain HTML/CSS for letter size, and renders two Code 128 barcodes
  (operation number, finished product code) with `jsbarcode` 3.11.6.
  TODO(OPEN-12) for label printer integration.
- **Inventory reserved drill-down.** Clicking a non-zero *Reservado* opens the
  holding orders (`GET /inventory/reservations`); rows link to the order only
  for users with `orders.view`.
- **404 wording.** `not_found()` uses the feminine form for feminine labels
  (`Orden no encontrada`, `Razón social …`, `Máquina …`, `Secuencia …`).
