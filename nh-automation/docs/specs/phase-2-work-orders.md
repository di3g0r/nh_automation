# Phase 2 — Work Orders and Reservations

> Status: v3 — 2026-10-13. Prerequisites: phases 0, 1 and **1b** done. Read `00-overview.md` and `01-data-model.md` (v3) first. See `CONTEXT.md` §6 for the paper form this replaces.
> Goal: admins and the Production manager create, edit, cancel and print work orders with one or more base products; stock is reserved and overselling is blocked.
> v3 changes: *Producto base / Producto terminado*; Retrabajo checkbox (type immutable); `T-`/`R-` numbering; no approval step; expiry left blank (set in phase 3 by the Production manager); comments as an append-only list; edits allowed until production starts.

## Scope

**In:** work orders CRUD, operation numbers, one or more base products, reservations, overselling block, packaging warnings, rework kinds, comments, cancellation, history, printable order.
**Out:** expiry entry, machine assignment, production, completion and closing (phase 3). Statuses after `created` exist in the enum but are not reachable yet.

## Tables

`reservations`, `work_orders`, `order_base_products`, `order_packaging`, `order_checklist` (create the 4 checklist rows with each order), `order_comments`. Add the foreign keys from `stock_movements.order_id` to `work_orders`.

## Requirements

### Order form (follows the paper form)
| Field | Rules |
|---|---|
| ☐ Retrabajo | Checkbox at the top of the **new order** form. Checked → Retrabajo, unchecked → Trabajo. **Cannot be changed after creation** (shown read-only when editing). The type is displayed prominently (badge *TRABAJO* / *RETRABAJO*) on every order screen and print |
| Tipo de retrabajo | Only for Retrabajo: *De una orden anterior* / *De inventario propio* (BR-21) |
| Orden relacionada | Required for *De una orden anterior*: search-select of completed/closed orders. Selecting it prefills client, finished product and expiry (copied and locked, BR-20) |
| Cliente | Required, active clients; hidden and null for *De inventario propio* |
| Lugar | Default site preselected |
| Fecha | Default today (local) |
| **Producto base** | **One or more rows**: product + liters (> 0). Add/remove rows; the same product cannot appear twice. Each row shows *Disponible: X L* live (red if insufficient) and the product's razón social |
| **Producto terminado** | One product + liters (> 0); defaults to the sum of base product liters, editable |
| Razón social | Automatic when all base products share one (read-only display); otherwise a required select limited to the base products' razones sociales (BR-22). Products without a razón social cannot be used. Fixed after creation |
| Número de operación | Generated on save: `T-<n> <RS>` or `R-<n> <RS>` (BR-19). Read-only |
| Comentario | Optional text; saved as the first entry of `order_comments` |
| Material de empaque | Rows: packaging item + planned qty |
| Total etiquetas | Planned labels |
| Código de barras | 1 por envase / 2 por caja |
| Lote anterior | Text, optional **[OPEN-4]** |
| Fecha de caducidad | **Not in the creation form**; shown as *"Pendiente — la asigna el Jefe de producción"* (except Retrabajo de orden anterior, where the copied expiry is shown locked) |

- **FR-ORD-1** Product code, name, provider, presentation and razón social code are **snapshotted** on save (base products and finished product).
- **FR-ORD-2** List with filters (status, type, date range, client, razón social, product — matching any base product or the finished product — site) and search by operation number; default sort newest first.
- **FR-ORD-3** Detail page with tabs: Información, Materiales, Checklist (read-only for now), **Comentarios** (list newest first + *Agregar comentario* for `orders.comment`; allowed in any status, including closed and cancelled), Historial (audit log + status changes). The Máquinas tab arrives in phase 3.
- **FR-ORD-4 / BR-16** Editing: users with `orders.edit` (master admin, admin, Production manager) can edit the order as many times as needed while it is `created` (in phase 3 also `assigned`), except type and razón social. Once production starts, the form is read-only.
- **FR-ORD-5 / BR-17** Delete only in `created`. Cancel (mandatory reason) in `created` or `assigned`, by master admin, admin and Production manager; never operators.
- **FR-ORD-6** Printable view replicating the paper form layout: header with type badge, operation number and razón social; *Producto base* table with **all rows**; *Producto terminado*; packaging table; checklist; lots; expiry (or *Pendiente*); comments; names + dates of who created, assigned, closed (filled as they happen); Code 128 barcode with the operation number and finished product code. **[OPEN-12]**

### Reservations (FR-INV-5…9)
- **FR-INV-5** On create: reserve each base product's liters (order site) and the planned packaging quantities.
- **FR-INV-6 / BR-2** Block when any base product's available < its liters. Spanish error per product, e.g. *"Inventario insuficiente de BASE CALCIO: existencia 1,500.00 L, reservado 1,000.00 L, disponible 500.00 L."* plus the orders holding reservations.
- **BR-3** Atomic and concurrency-safe; lock stock rows in a fixed order.
- **FR-INV-7 / BR-4** Packaging shortage → warning shown in the form and stored in `warnings`; save still allowed.
- On edit: recompute reservations (release old, reserve new) in one transaction.
- **BR-10** Cancel/delete releases reservations.
- Inventory screen shows real *reserved* and *available*; clicking reserved shows the orders.
- *Retrabajo de inventario propio* reserves its base products like any order (the product being reworked is the base product).

### API endpoints
`GET/POST /orders`, `GET/PATCH/DELETE /orders/{id}`, `POST /orders/{id}/cancel` (`{reason}`), `GET/POST /orders/{id}/comments`, `GET /orders/{id}/history`, `GET /orders/{id}/print-data`, `GET /inventory/availability` (used live by the form). Payloads use `base_products: [{product_id, liters}]`, `finished_product_id`, `finished_liters`, `order_type` (create only), `rework_kind`.

### Frontend
- **Órdenes** list with status and type badges and filters.
- **Nueva orden / Editar orden** form laid out like the paper form (sections: Información general, Producto base, Producto terminado, Material de empaque, Comentario, Trazabilidad). The form adapts to the Retrabajo checkbox and Tipo de retrabajo.
- **Detalle de orden** with action buttons by status and permission: Editar, Cancelar, Eliminar, Imprimir, Agregar comentario.
- **Imprimir** page with print-optimized CSS (letter size).

## Tests
- Create reserves stock for every base product; available decreases (BR-1).
- Overselling blocked when one of several base products is short; the error lists that product only (BR-2).
- Concurrent creates for the last liters: exactly one succeeds; two orders locking the same two products in different row orders do not deadlock (BR-3).
- Numbering: Trabajo and Retrabajo sequences independent and shared across razones sociales (`T-1 NB`, `T-2 ANB`, `R-1 NB`); deleted order leaves a gap; concurrent creates get distinct numbers (BR-19).
- Order type cannot be changed via PATCH (BR-21).
- Razón social automatic when shared; required choice when mixed; choice outside the base products' razones sociales rejected; product without razón social rejected (BR-22).
- Rework: previous-order requires a completed/closed related order and copies its expiry (locked); own-stock has no client and no expiry yet (BR-20, BR-21). (Until phase 3 there are no completed orders; test with a fixture.)
- Edit in `created` changing a base product re-reserves; edit refused once production started (fixture).
- Comments can be added in any status by admin and Production manager; operator gets 403.
- Cancel/delete releases reservations; Production manager can cancel; operator cannot.
- Snapshots preserved after product rename.

## Acceptance scenarios
1. With 1,500 L BASE CALCIO (ANB) on hand, an admin creates a Trabajo for a client: Producto base 1,000 L BASE CALCIO → Producto terminado 1,000 L NH-CALCIO 1X20, 50 × ENVLI20001, 50 labels → number `T-1 ANB`; expiry shows *Pendiente*; BASE CALCIO shows 1,000 L reserved, 500 L available.
2. A second order for 800 L BASE CALCIO is blocked showing 500 L available and `T-1 ANB` holding the reservation.
3. Mixed Trabajo: 600 L of an NB product + 400 L of an ANB product → the user must choose NB or ANB; choosing NB gives `T-2 NB`.
4. Retrabajo de inventario propio (checkbox checked): 100 L of a product with a damaged container → no client field → `R-1 <RS>`. Editing it does not offer to change it to Trabajo.
5. The Production manager edits `T-1 ANB` twice (comment, packaging) and adds a comment; both appear with author and time.
6. Packaging with 10 units of ENVLI20001 on hand → order saves with a warning.
7. Printed order resembles the paper form, shows the type badge and lists all base products.

## Definition of done
- [ ] Scenarios above pass manually and in automated tests.
- [ ] Audit log records create/edit/cancel/delete/comment.
- [ ] Tests pass; `docs/PROGRESS.md` updated.
