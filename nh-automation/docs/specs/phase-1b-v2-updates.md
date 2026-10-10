# Phase 1b — Apply v2 Decisions to Phases 0–1

> Prerequisites: phases 0–1 done. Read `docs/CONTEXT.md` (v2), `00-overview.md` and `01-data-model.md` (v2) first.
> Goal: bring the code already built in line with the owner's decisions of 2026-10-09, before phase 2 starts. Small, focused session.

## What changed (summary)

- Every product belongs to a **razón social** (NB, ANB and two more). The operation number suffix comes from the razón social, with a separate sequence each.
- NOBELTECH and AGRONB are **razones sociales, not clients**.
- **Supervisors can cancel orders** (permission only; orders arrive in phase 2).
- Expiry defaults to **3 years** (new setting).
- **No VPN**, and PLCs will access the database directly (phase 4) — no code exists yet for either, so nothing to remove; just make sure no VPN references remain in README/deploy docs.

## Tasks

### 1. Razones sociales
- Table `razones_sociales` (code unique, name, next_number ≥ 1, is_active) — migration seeds `NB` NOBELTECH, `ANB` AGRONB, `RS3` "Razón social 3 (por definir)", `RS4` "Razón social 4 (por definir)", all with `next_number = 1`. `TODO(OPEN-16)`, `TODO(OPEN-17)`.
- Catalog screen **Razones sociales** (list, create, edit, activate/deactivate) under Catálogos, permission `catalogs.manage`.
- `next_number` is editable only with the new permission `sequences.manage` (master admin), shown in the same screen with a warning: *"Cambiar el siguiente número afecta la numeración de nuevas órdenes."* Must be ≥ 1. Audited.
- Code rules: uppercase letters/digits, 1–6 characters; cannot be changed once any order uses it (enforce in phase 2; for now, allow edits).

### 2. Products
- Add `products.razon_social_id` (FK, nullable in the DB).
- Product form: razón social **required** (select of active razones sociales). List: new column and filter.
- Products without a razón social show a badge *"Sin razón social"* and a filter to find them. (Phase 2 will refuse them as order sources.)
- **Import** (external DB and CSV/XLSX): new canonical column `razon_social` holding the code, with aliases (`razon_social`, `razón social`, `rs`, `empresa`). Unknown code → row error. Empty → row warning (product imported without razón social). In upsert mode, empty never clears an existing value (current rule). Update `backend/external_sources/*.sql.example` and the samples in `tools/samples/`.
- Dev seed: assign NB to GRN100C1XL20F004 and ANB to the QVR products.

### 3. Clients seed correction
- New migration: deactivate the seeded clients NOBELTECH and AGRONB (they are razones sociales). Do not delete them. Remove them from `seed-catalogs`; add two clearly fake sample clients to `seed-dev` only.

### 4. Permissions and settings
- Add `orders.cancel` to supervisor in `app/core/permissions.py`. Add `sequences.manage` (master admin) and `machines.plc_credentials` (master admin, used in phase 4).
- New setting `default_shelf_life_years` = 3 (integer 1–10), editable in Configuración, with Spanish label *"Vida útil predeterminada (años)"*.
- Update the permission matrix tests.

### 5. Docs
- README / deploy docs: no VPN references; access is LAN only.
- `CLAUDE.md` command table: update the `seed-catalogs` description (site, razones sociales, packaging items).
- Record decisions in `docs/DECISIONS.md` and the session in `docs/PROGRESS.md`.

## Tests
- Razón social CRUD, unique code, `next_number` permission (admin 403, master admin OK), audit entry.
- Product create/edit requires razón social; list filter "sin razón social".
- Import: valid code, unknown code (error, nothing saved), empty (warning), upsert doesn't clear.
- Supervisor has `orders.cancel`; operator doesn't.
- Setting `default_shelf_life_years` validation.

## Definition of done
- [ ] Migrations apply on the dev stack; `alembic check` shows no drift.
- [ ] Razones sociales visible and editable in Spanish UI; products show their razón social.
- [ ] Sample CSV with a `razon_social` column imports correctly.
- [ ] NOBELTECH/AGRONB no longer active as clients.
- [ ] All tests, lint and type checks pass; `docs/PROGRESS.md` updated.
