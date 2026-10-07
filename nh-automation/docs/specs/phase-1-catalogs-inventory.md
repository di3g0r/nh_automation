# Phase 1 — Catalogs and Inventory

> Prerequisites: phase 0 done. Read `00-overview.md` and `01-data-model.md` first.
> Goal: products, packaging, clients, sites and machines managed in the app; current spreadsheets imported; stock visible with receipts and adjustments.

## Scope

**In:** catalog CRUD, CSV/XLSX import, stock levels, movements, receipts, adjustments, low-stock and negative-stock alerts, seed data.
**Out:** reservations (phase 2; "reserved" shows 0 for now but the column exists in the UI and API).

## Tables

`sites`, `clients`, `products`, `packaging_items`, `machines`, `stock_levels`, `stock_movements`.

## Requirements

### Catalogs (FR-CAT)
- **FR-CAT-1 Products:** code (unique), name, provider, presentation, container_liters (optional), active.
- **FR-CAT-2 Packaging items:** code (unique), description, category, low-stock threshold, active. Seed the 14 items (`01-data-model.md` §5).
- **FR-CAT-3 Clients:** name, short code (unique), active. Only a list; no other client features.
- **FR-CAT-4 Sites:** name, active, exactly one default.
- **FR-CAT-5 Machines:** code, name, site, active, maintenance flag. API key generated on creation/rotation, **shown once**, stored hashed (used in phase 4).
- **FR-CAT-6** Items referenced elsewhere are deactivated, not deleted. Inactive items cannot be selected in new records but still display in old ones.
- **FR-CAT-7 Import:** upload CSV or XLSX for products and packaging items → preview table with per-row errors (missing fields, duplicates, invalid numbers) → confirm to save. Option: create new only / create or update. Optional initial stock column per default site (writes `receipt` movements with note "Importación inicial").

### Inventory (FR-INV)
- Products in liters (2 decimals); packaging in units. Stock per site.
- **FR-INV-1** Inventory screen: products and packaging tabs; columns code, name, site, on hand, reserved, available; filters (site, category, low stock, negative stock, search).
- **FR-INV-2 Receipt (Entrada):** item, site, quantity > 0, note → `receipt` movement.
- **FR-INV-3 Adjustment (Ajuste):** item, site, new counted quantity (system computes delta) and mandatory reason → `adjustment` movement.
- **FR-INV-4** Movements list: filters by item, site, type, date range, user; each row links to order/assignment when present.
- **FR-INV-10/11** Alerts: packaging available below threshold (low stock) and any negative on-hand. Shown as badges in inventory and as a count in the top bar.
- Stock service functions (used by later phases): `get_available(item, site)`, `apply_movement(...)` with row lock (BR-3, BR-5).

### API endpoints
`GET/POST /products`, `GET/PATCH /products/{id}` (same for `/packaging-items`, `/clients`, `/sites`, `/machines`); `POST /machines/{id}/rotate-key`; `POST /imports/{products|packaging-items}/preview`, `POST /imports/{...}/confirm`; `GET /inventory`, `GET /inventory/movements`, `POST /inventory/receipts`, `POST /inventory/adjustments`, `GET /inventory/availability?item_type=&item_id=&site_id=`; `GET /inventory/alerts`.

All catalog and inventory writes go to the audit log.

### Frontend
- **Catálogos**: Productos, Materiales de empaque, Clientes, Sitios, Máquinas — list with search + active filter, create/edit form, activate/deactivate. Machine key shown once in a dialog with copy button.
- **Importar** dialog on Productos and Materiales de empaque with preview and error highlighting.
- **Inventario**: tabs Productos / Materiales de empaque, **Movimientos**, buttons **Entrada** and **Ajuste**.
- **Inicio**: stock alerts card.

## Tests
- Unique code validation; deactivation rules.
- Import: valid file, file with errors (nothing saved), update mode.
- Receipt and adjustment create movements and update on hand; adjustment requires reason.
- Concurrent movements on the same item keep totals consistent.
- Low-stock and negative-stock alerts.
- Permissions per role (supervisor can move stock but not edit catalogs; operator has no access).

## Definition of done
- [ ] All catalogs manageable in Spanish UI; seed data present.
- [ ] A sample product spreadsheet imports correctly; errors are shown before saving.
- [ ] Receipts and adjustments update stock with movements and audit entries.
- [ ] Alerts visible.
- [ ] Tests pass; `docs/PROGRESS.md` updated.
