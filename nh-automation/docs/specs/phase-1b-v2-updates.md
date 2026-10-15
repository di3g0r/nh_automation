# Phase 1b — Apply v2/v3 Decisions to Phases 0–1

> Status: v3 — 2026-10-13. Prerequisites: phases 0–1 done. Read `docs/CONTEXT.md` (v3), `00-overview.md` and `01-data-model.md` (v3) first.
> Goal: bring the code already built in line with the owner's decisions of 2026-10-09 and 2026-10-13, before phase 2 starts. Small, focused session.

## What changed (summary)

- Every product belongs to a **razón social** (NB, ANB and two more).
- Operation numbers: **one sequence for Trabajo (`T-`) and one for Retrabajo (`R-`)**, shared by all razones sociales, starting at 1.
- NOBELTECH and AGRONB are **razones sociales, not clients**.
- New role **Production manager** (`production_manager`, *Jefe de producción*) **replaces the supervisor**. New permission set (overview §4).
- No automatic expiry default (the Production manager enters it); the 3-year setting is **not** created.
- Acceptable difference range: two settings.
- **No VPN**; nothing to remove in code, only check docs.

## Tasks

### 1. Roles and permissions
- Replace role `supervisor` with `production_manager` everywhere (enum/check constraint, permission map, UI labels, seed-dev, tests). Migration: convert any existing `supervisor` users to `production_manager`.
- Spanish label: *Jefe de producción*.
- Rewrite `app/core/permissions.py` to match overview §4 exactly (adds `orders.comment`, `orders.expiry`, `orders.close`, `production.control`, `sequences.manage`, `machines.plc_credentials`; removes `orders.approve`, `orders.verify`, `assignments.work_own`). Only permissions with existing endpoints get wired now; the rest are defined for later phases.
- `inventory.move` is now master admin + admin only (the Production manager can only view inventory). Update endpoints and tests.
- Frontend: the Production manager lands on a placeholder **Producción** page (filled in phase 3); navigation per overview §6.

### 2. Razones sociales
- Table `razones_sociales` (code unique, name, is_active) — migration seeds `NB` NOBELTECH, `ANB` AGRONB, `RS3` "Razón social 3 (por definir)", `RS4` "Razón social 4 (por definir)". `TODO(OPEN-16)`.
- Catalog screen **Razones sociales** (list, create, edit, activate/deactivate) under Catálogos, permission `catalogs.manage`.
- Code rules: uppercase letters/digits, 1–6 characters. (Phase 2 will block changing a code already used by an order.)

### 3. Order sequences
- Table `order_sequences` seeded with `trabajo` (prefix `T`, next_number 1) and `retrabajo` (prefix `R`, next_number 1).
- Master admin (`sequences.manage`) can view and change `next_number` (≥ 1) in **Configuración**, with the warning *"Cambiar el siguiente número afecta la numeración de nuevas órdenes."* Audited. Phase 2 uses the table.

### 4. Products
- Add `products.razon_social_id` (FK, nullable in the DB).
- Product form: razón social **required** (select of active razones sociales). List: new column and filter.
- Products without a razón social show a badge *"Sin razón social"* and a filter to find them. (Phase 2 will refuse them as base products.)
- **Import** (external DB and CSV/XLSX): new canonical column `razon_social` holding the code, with aliases (`razon_social`, `razón social`, `rs`, `empresa`). Unknown code → row error. Empty → row warning (imported without razón social). In upsert mode, empty never clears an existing value. Update `backend/external_sources/*.sql.example` and `tools/samples/`.
- Dev seed: assign NB to GRN100C1XL20F004 and ANB to the QVR products.

### 5. Clients seed correction
- New migration: deactivate the seeded clients NOBELTECH and AGRONB (they are razones sociales). Do not delete them. Remove them from `seed-catalogs`; add two clearly fake sample clients to `seed-dev` only.

### 6. Settings
- Keep `difference_tolerance_liters` (default 0). Add `difference_tolerance_percent` (default 0, 0–100, 2 decimals). Spanish labels: *"Tolerancia de diferencia (L)"*, *"Tolerancia de diferencia (%)"*. `TODO(OPEN-19)`.
- Remove `approver_must_differ` (there is no approval step any more) via migration.
- Do **not** add a shelf-life/expiry default setting.

### 7. Docs
- README / deploy docs: no VPN references; access is LAN only.
- `CLAUDE.md` command table: update the `seed-catalogs` description (site, razones sociales, order sequences, packaging items) and the `seed-dev` description (one user per role: master admin, admin, jefe de producción, operador).
- Record decisions in `docs/DECISIONS.md` and the session in `docs/PROGRESS.md`.

## Tests
- Role migration: a `supervisor` user becomes `production_manager`; the role list no longer accepts `supervisor`.
- Full permission matrix per overview §4 for the endpoints that exist (including: Production manager can view inventory but not create receipts/adjustments).
- Razón social CRUD, unique code, audit entry.
- Order sequences: master admin can change `next_number`; admin gets 403; value ≥ 1.
- Product create/edit requires razón social; list filter "sin razón social".
- Import: valid code, unknown code (error, nothing saved), empty (warning), upsert doesn't clear.
- Settings: tolerance validation; `approver_must_differ` gone.

## Definition of done
- [ ] Migrations apply on the dev stack; `alembic check` shows no drift.
- [ ] A *Jefe de producción* user can log in and lands on the Producción placeholder.
- [ ] Razones sociales visible and editable in Spanish UI; products show their razón social.
- [ ] Sequences visible and editable by the master admin in Configuración.
- [ ] Sample CSV with a `razon_social` column imports correctly.
- [ ] NOBELTECH/AGRONB no longer active as clients.
- [ ] All tests, lint and type checks pass; `docs/PROGRESS.md` updated.
