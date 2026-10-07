# Phase 2 — Work Orders and Reservations

> Prerequisites: phases 0–1 done. Read `00-overview.md` and `01-data-model.md` first. See `CONTEXT.md` §6 for the paper form this replaces.
> Goal: admins create, edit, approve, cancel and print work orders; stock is reserved and overselling is blocked.

## Scope

**In:** work orders CRUD, operation numbers, reservations, overselling block, packaging warnings, approval, cancellation, history, printable order.
**Out:** assignments, machine/operator work, completion, verification (phase 3). The *Asignada* and later statuses exist in the enum but are not reachable yet.

## Tables

`reservations`, `work_orders`, `order_packaging`, `order_checklist` (create the 4 checklist rows with each order).

## Requirements

### Order fields (follow the paper form)
| Field | Rules |
|---|---|
| Número de operación | Auto: `<global sequence> <client code>` e.g. `8292 ANB`; read-only **[OPEN-2]**. Sequence starting value configurable (so it can continue from the current paper numbering). |
| Tipo | Trabajo / Retrabajo |
| Orden relacionada | Optional search-select of a previous order **[OPEN-1]** |
| Cliente | Required, active clients |
| Lugar | Default site preselected |
| Fecha | Default today (local) |
| ANTES | Source product + liters (> 0) |
| DESPUÉS | Result product + liters (> 0); defaults to ANTES liters |
| Comentarios / operación | Free text |
| Material de empaque | Rows: packaging item + planned qty |
| Total etiquetas | Planned labels |
| Código de barras | 1 por envase / 2 por caja |
| Lote anterior, Lote posterior, Fecha de caducidad | Text, optional at creation **[OPEN-4]** |

- **FR-ORD-1** Product code, name, provider, presentation are **snapshotted** on save.
- **FR-ORD-2** List with filters (status, date range, client, product, site) and search by operation number; default sort newest first.
- **FR-ORD-3** Detail page with tabs: Información, Materiales, Checklist (read-only for now), Historial (from audit log + status changes). Assignments tab added in phase 3.
- **FR-ORD-4 / BR-16** Editing rules by status.
- **FR-ORD-5 / BR-17** Delete only in *Creada*; otherwise cancel with mandatory reason.
- **FR-ORD-6** Printable view (`/orders/{id}/print`, browser print to PDF/paper) replicating the paper form layout: header, ANTES/DESPUÉS table, packaging table, checklist, lots, expiry, signature boxes filled with user names + dates from the system, and a Code 128 barcode with the operation sequence and result product code. **[OPEN-12]**
- **FR-ORD-7** Approve: records approver/time; if setting `approver_must_differ` is on, creator cannot approve.

### Reservations (FR-INV-5…9)
- **FR-INV-5** On create: reserve source liters (source product, order site) and planned packaging quantities.
- **FR-INV-6 / BR-2** Block when source available < source liters. Spanish error, e.g. *"Inventario insuficiente de BASE CALCIO: existencia 1,500.00 L, reservado 1,000.00 L, disponible 500.00 L."* plus the list of orders holding reservations.
- **BR-3** Atomic and concurrency-safe.
- **FR-INV-7 / BR-4** Packaging shortage → warning shown in the form and stored in `warnings`; save still allowed.
- On edit: recompute reservations (release old, reserve new) in one transaction.
- **FR-INV-9 / BR-10** Cancel/delete releases reservations.
- Inventory screen now shows real *reserved* and *available*; clicking reserved shows the orders.

### API endpoints
`GET/POST /orders`, `GET/PATCH/DELETE /orders/{id}`, `POST /orders/{id}/approve`, `POST /orders/{id}/cancel` (`{reason}`), `GET /orders/{id}/history`, `GET /orders/{id}/print-data`, `GET /inventory/availability` (used live by the form).

### Frontend
- **Órdenes** list with status badges and filters.
- **Nueva orden / Editar orden** form laid out like the paper form (sections: Información general, Información cuantitativa, Material de empaque, Comentarios, Trazabilidad). Next to the source product: live *Disponible: X L* (red if insufficient). Packaging rows show available units and a warning icon if short.
- **Detalle de orden** with action buttons by status and permission: Editar, Aprobar, Cancelar, Eliminar, Imprimir.
- **Imprimir** page with print-optimized CSS (letter size).

## Tests
- Create reserves stock; available decreases (BR-1).
- Overselling blocked with correct numbers (acceptance scenario 2 below).
- Concurrent creates for the last liters: exactly one succeeds (BR-3).
- Edit in *Aprobada* changing liters returns to *Creada* and re-reserves.
- Cancel/delete releases reservations.
- Invalid transitions rejected (BR-6).
- Operation number format and uniqueness; sequence start value respected.
- Snapshot preserved after product rename.

## Acceptance scenarios
1. With 1,500 L BASE CALCIO on hand, admin creates order: ANTES 1,000 L BASE CALCIO → DESPUÉS 1,000 L NH-CALCIO 1X20, 50 × ENVLI20001, 50 labels, client AGRONB → number like `8292 ANB`; BASE CALCIO shows 1,000 L reserved, 500 L available.
2. A second order for 800 L BASE CALCIO is blocked showing 500 L available and order `8292 ANB` holding the reservation.
3. Packaging with 10 units of ENVLI20001 on hand → order saves with a warning.
4. Printed order resembles the paper form.

## Definition of done
- [ ] Scenarios above pass manually and in automated tests.
- [ ] Audit log records create/edit/approve/cancel/delete.
- [ ] Tests pass; `docs/PROGRESS.md` updated.
