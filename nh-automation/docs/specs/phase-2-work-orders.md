# Phase 2 — Work Orders and Reservations

> Status: v2 — 2026-10-09. Prerequisites: phases 0, 1 and **1b** done. Read `00-overview.md` and `01-data-model.md` (v2) first. See `CONTEXT.md` §6 for the paper form this replaces.
> Goal: admins create, edit, approve, cancel and print work orders with one or more source products; stock is reserved and overselling is blocked.
> v2 changes: several source products (ANTES), razón social and per-razón-social numbering, rework kinds, expiry rules, supervisor can cancel.

## Scope

**In:** work orders CRUD, operation numbers per razón social, several source products, reservations, overselling block, packaging warnings, rework kinds, expiry defaults, approval, cancellation, history, printable order.
**Out:** assignments, machine/operator work, completion, verification (phase 3). The *Asignada* and later statuses exist in the enum but are not reachable yet.

## Tables

`reservations`, `work_orders`, `order_sources`, `order_packaging`, `order_checklist` (create the 4 checklist rows with each order). Add the foreign keys from `stock_movements.order_id` to `work_orders`.

## Requirements

### Order fields (follow the paper form)
| Field | Rules |
|---|---|
| Tipo | Trabajo / Retrabajo |
| Tipo de retrabajo | Only for Retrabajo: *De una orden anterior* / *De inventario propio* (BR-21) |
| Orden relacionada | Required for *De una orden anterior*: search-select of completed/verified orders. Selecting it prefills client, result product and expiry |
| Cliente | Required, active clients; hidden and null for *De inventario propio* |
| Lugar | Default site preselected |
| Fecha | Default today (local) |
| ANTES | **One or more rows**: source product + liters (> 0). Add/remove rows; the same product cannot appear twice. Each row shows *Disponible: X L* live (red if insufficient) and the product's razón social |
| DESPUÉS | One result product + liters (> 0); defaults to the sum of ANTES liters, editable |
| Razón social | Automatic when all ANTES products share one (read-only display); otherwise a required select limited to the ANTES products' razones sociales (BR-22). Products without a razón social cannot be used as sources |
| Número de operación | Generated on save: `<next number of the razón social> <code>`, e.g. `8292 ANB` (BR-19). Read-only; razón social cannot change after creation |
| Comentarios / operación | Free text |
| Material de empaque | Rows: packaging item + planned qty |
| Total etiquetas | Planned labels |
| Código de barras | 1 por envase / 2 por caja |
| Lote anterior, Lote posterior | Text, optional at creation **[OPEN-4]** |
| Fecha de caducidad | Month/year picker, shown `MM/AAAA`. Default per BR-20: Trabajo = order date + `default_shelf_life_years` (3); Retrabajo de orden anterior = related order's expiry; Retrabajo de inventario propio = empty and required before approval. Always editable until verified. A hint shows where the default came from |

- **FR-ORD-1** Product code, name, provider, presentation and razón social code are **snapshotted** on save (sources and result).
- **FR-ORD-2** List with filters (status, date range, client, razón social, type, product — matching any source or the result — site) and search by operation number; default sort newest first.
- **FR-ORD-3** Detail page with tabs: Información, Materiales, Checklist (read-only for now), Historial (from audit log + status changes). Assignments tab added in phase 3.
- **FR-ORD-4 / BR-16** Editing rules by status. Adding/removing/changing ANTES rows counts as changing quantities.
- **FR-ORD-5 / BR-17** Delete only in *Creada*; otherwise cancel with mandatory reason. Cancel allowed for master admin, admin and supervisor, only in *Creada*, *Aprobada*, *Asignada*.
- **FR-ORD-6** Printable view replicating the paper form layout: header (with razón social), ANTES table with **all source rows**, DESPUÉS, packaging table, checklist, lots, expiry, signature boxes filled with user names + dates from the system, and a Code 128 barcode with the operation number and result product code. **[OPEN-12]**
- **FR-ORD-7** Approve: records approver/time; if setting `approver_must_differ` is on, creator cannot approve. *Retrabajo de inventario propio* cannot be approved without an expiry date.

### Reservations (FR-INV-5…9)
- **FR-INV-5** On create: reserve each source product's liters (order site) and the planned packaging quantities.
- **FR-INV-6 / BR-2** Block when any source product's available < its liters. Spanish error per product, e.g. *"Inventario insuficiente de BASE CALCIO: existencia 1,500.00 L, reservado 1,000.00 L, disponible 500.00 L."* plus the orders holding reservations.
- **BR-3** Atomic and concurrency-safe; lock stock rows in a fixed order.
- **FR-INV-7 / BR-4** Packaging shortage → warning shown in the form and stored in `warnings`; save still allowed.
- On edit: recompute reservations (release old, reserve new) in one transaction.
- **FR-INV-9 / BR-10** Cancel/delete releases reservations.
- Inventory screen shows real *reserved* and *available*; clicking reserved shows the orders.
- *Retrabajo de inventario propio* reserves its sources like any order (the product being reworked is the source).

### API endpoints
`GET/POST /orders`, `GET/PATCH/DELETE /orders/{id}`, `POST /orders/{id}/approve`, `POST /orders/{id}/cancel` (`{reason}`), `GET /orders/{id}/history`, `GET /orders/{id}/print-data`, `GET /orders/expiry-default?type=&rework_kind=&related_order_id=&order_date=`, `GET /inventory/availability` (used live by the form). Order payloads carry `sources: [{product_id, liters}]`.

### Frontend
- **Órdenes** list with status badges and filters.
- **Nueva orden / Editar orden** form laid out like the paper form (sections: Información general, Información cuantitativa — ANTES rows + DESPUÉS, Material de empaque, Comentarios, Trazabilidad). The form adapts to Tipo / Tipo de retrabajo.
- **Detalle de orden** with action buttons by status and permission: Editar, Aprobar, Cancelar, Eliminar, Imprimir.
- **Imprimir** page with print-optimized CSS (letter size).

## Tests
- Create reserves stock for every source; available decreases (BR-1).
- Overselling blocked when one of several sources is short; error lists that product only (BR-2).
- Concurrent creates for the last liters: exactly one succeeds; two orders locking the same two products in different row orders do not deadlock (BR-3).
- Numbering: separate sequences per razón social; `next_number` increments; deleted order leaves a gap; concurrent creates get distinct numbers (BR-19).
- Razón social: automatic when shared; required choice when mixed; choice outside the sources' razones sociales rejected; product without razón social rejected (BR-22).
- Rework: previous-order requires a completed/verified related order and copies its expiry; own-stock has no client and needs an expiry before approval (BR-20, BR-21).
- Trabajo expiry defaults to order date + 3 years and follows the setting.
- Edit in *Aprobada* changing a source returns to *Creada* and re-reserves.
- Cancel/delete releases reservations; supervisor can cancel; operator cannot; cancel after *Asignada* is impossible in this phase (state not reachable) but the rule is enforced by the transition table.
- Snapshots preserved after product rename.

## Acceptance scenarios
1. With 1,500 L BASE CALCIO (ANB) on hand, admin creates a Trabajo for a client: ANTES 1,000 L BASE CALCIO → DESPUÉS 1,000 L NH-CALCIO 1X20, 50 × ENVLI20001, 50 labels → number `<n> ANB`; expiry prefilled 3 years ahead; BASE CALCIO shows 1,000 L reserved, 500 L available.
2. A second order for 800 L BASE CALCIO is blocked showing 500 L available and the first order holding the reservation.
3. Mixed order: ANTES 600 L of an NB product + 400 L of an ANB product → the user must choose NB or ANB; choosing NB gives the next NB number; both products reserved.
4. Retrabajo de inventario propio: ANTES 100 L of a product with a damaged container → no client field, expiry required before approval.
5. Retrabajo de una orden anterior: selecting order from scenario 1 prefills client, product and its expiry.
6. Packaging with 10 units of ENVLI20001 on hand → order saves with a warning.
7. Printed order resembles the paper form and lists all ANTES rows.

## Definition of done
- [ ] Scenarios above pass manually and in automated tests.
- [ ] Audit log records create/edit/approve/cancel/delete.
- [ ] Tests pass; `docs/PROGRESS.md` updated.
