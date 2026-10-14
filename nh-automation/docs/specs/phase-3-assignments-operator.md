# Phase 3 — Production Manager, Machines, Production Controls and Closing

> Status: v3.1 — 2026-10-13. Prerequisites: phases 0–2 done. Read `00-overview.md` and `01-data-model.md` (v3.1) first.
> Goal: the full process runs without paper and **without PLCs**: the Production manager completes and assigns new orders to machines → production is recorded (start, pause, resume, complete) from the platform → completion moves stock → the Production manager closes the order.
> v3.1: **operators do not use the platform** (they only see the PLC screen). There is no operator station; this phase also removes the operator role and PIN login from the UI. Production controls are used by the Production manager until the PLCs write them (phase 4).

## Scope

**In:** Producción screen, expiry entry, machine assignment and split, machine queues, machine board, production controls in the platform (start/pause/resume/complete), traceability (lots, checklist, actual materials and labels), completion with stock movements, differences, closing, removal of the operator role from the UI.
**Out:** the PLC database interface (phase 4). Design the assignment service so phase 4's event processor can call the same functions with `source="plc"` and a machine (instead of a user) as the actor.

## Tables

`assignments`, `assignment_events`.

## Requirements

### 0. Operators leave the platform
- Remove *Operador* from the role options when creating/editing users; the API rejects creating users with role `operator`.
- Users with role `operator` cannot log in (Spanish message: *"Los operadores no usan la plataforma."*). Keep `operator` in the DB constraint so existing rows stay valid (DECISIONS). Deactivate any existing operator users in a migration (audited).
- Remove PIN login (endpoint, login tab, PIN fields in user forms). Keep the `pin_hash` column (unused) to avoid a destructive migration.
- Remove the operator placeholder page and the operator landing rule.
- Update `seed-dev` (no operator user), the permission map (overview §4, three roles) and the permission tests.

### Producción (Production manager's home)
- **FR-PM-1** Three sections, auto-refresh every 10 s:
  - **Por asignar**: orders in `created`, newest first, showing what is missing: *Falta fecha de caducidad*, *Falta asignar máquinas*.
  - **En producción**: orders `assigned`, `in_progress`, `paused`, with per-machine status and liters, and the production controls (below).
  - **Por cerrar**: orders in `completed`, with ordered vs actual liters and the difference highlighted when outside the acceptable range (BR-12).
- Visible to users with `orders.assign` (Production manager, master admin).

### Expiry (BR-20)
- **FR-PM-2** Users with `orders.expiry` enter the expiry (month/year picker, shown `MM/AAAA`).
- Trabajo: editable until production starts. Retrabajo de orden anterior: already copied and locked. Retrabajo de inventario propio: entered once, then locked (confirm dialog: *"La fecha de caducidad de un retrabajo no se podrá cambiar."*).
- Who and when are recorded.

### Machine assignment (BR-7, BR-14)
- **FR-ASG-1** Users with `orders.assign` assign a `created` order to **one or more machines** (typically 1 or 2), each with planned liters.
- The form shows each machine's state (Libre, Ocupada, En pausa, Mantenimiento) and queue length, and a running total: *Asignado 70.00 / 100.00 L — faltan 30.00 L*. Save is only allowed when the total equals the order's finished liters exactly.
- One assignment per machine per order. Inactive/maintenance machines cannot be chosen. Assigning to a busy machine is allowed (it queues) with a notice.
- When the expiry is set **and** the assignments add up, the order becomes `assigned`. Removing assignments or clearing a Trabajo expiry returns it to `created`.
- **FR-ASG-2** Before production starts, assignments can be changed (machines, liters) or removed. Once any assignment of the order has started, assignments are locked.
- **FR-ASG-3** Each machine has a queue by `queue_position`; users with `orders.assign` can reorder pending assignments on a machine. Only the first pending assignment of a machine can start, and only when no other assignment on that machine is running or paused (BR-14). (This queue is what the PLC screen will show, phase 4.)
- **BR-16 reminder:** if base products, liters or finished product of an `assigned` order are edited, the assignments are deleted and the order returns to *Por asignar*.

### Production controls in the platform (fallback to the PLC)
- **FR-PRD-1** Users with `production.control` (Production manager, master admin) see, per assignment, the buttons **Iniciar**, **Pausar**, **Reanudar**, **Terminar** (enter actual liters) in **Producción → En producción**, in the order's **Máquinas** tab and on the machine board. Recorded with `source="manual"` and the user.
- Until phase 4 these buttons are how production is recorded; afterwards the PLC writes these actions (the operator presses them on the machine's screen) and the buttons remain as a fallback, e.g. if a PLC fails.
- Confirmation dialog for **Terminar** showing planned liters and the entered actual liters.

### Pause and resume (BR-23)
- Pausing an assignment keeps its liters and reservations; the order shows **Pausada** when none of its machines is running (derived, data model §3). Each machine pauses independently.
- A paused assignment resumes on the same machine **[OPEN-20]**.

### Traceability (BR-24)
- In the order detail (tabs Checklist and Materiales) users with `orders.traceability` (master admin, admin, Production manager) fill: the 4 checklist items, lote posterior, actual packaging and labels used (prefilled with planned values). Each value records who and when. Editable until the order is closed.

### Completion (BR-8, BR-9, BR-10, BR-12)
- Completing an assignment with actual liters A, in one transaction: finished product +A; each base product −(its liters × A ÷ order finished liters); base product reservations reduced.
- Packaging is consumed **per order** when the order becomes `completed`: the actual quantities if already entered, otherwise the planned ones. If actual quantities are entered or changed afterwards (before closing), a correcting `consumption`/`adjustment` movement records only the difference. Packaging reservations are released at the same time.
- When every assignment is completed, the order becomes `completed` and remaining reservations are released (BR-10). It appears in **Por cerrar**.
- Difference shown as *Faltante* / *Excedente*, highlighted only when outside the range (`difference_tolerance_liters` or `difference_tolerance_percent`) **[OPEN-19]**.

### Closing (BR-11)
- Users with `orders.close` review a completed order: ordered vs actual liters, difference, per-machine results, checklist, lots, materials, comments. **Cerrar orden** with an optional note → `closed`.
- Closing is allowed even if the difference is outside the range or the checklist/lot/materials are incomplete; the dialog lists what is missing and asks for confirmation.
- Closed orders are read-only except comments.

### Machine board (FR-MCH)
- **FR-MCH-1** Card per machine: state (Libre, Ocupada, En pausa, Mantenimiento), current order + type, liters progress bar, queue length, production buttons for `production.control`. (*Último contacto del PLC* is added in phase 4.)
- **FR-MCH-2** Master admin, admin, Production manager; auto-refresh 5 s. Users with `catalogs.manage` can toggle maintenance. Add **Máquinas** to the navigation.

### Printing
- The printable order from phase 2 stays as an **optional** feature (nothing in the process depends on it). Update it to show assignments, expiry, actual results and who closed the order.

### API endpoints
`GET /production/to-assign`, `GET /production/in-production`, `GET /production/to-close`, `PUT /orders/{id}/expiry`, `PUT /orders/{id}/assignments` (replace the full split: `[{machine_id, planned_liters}]`), `PATCH /assignments/{id}/queue-position`, `GET /machines/{id}/queue`, `POST /assignments/{id}/start|pause|resume|complete`, `PATCH /orders/{id}/checklist`, `PATCH /orders/{id}/traceability` (lots), `PATCH /orders/{id}/materials` (actual packaging and labels), `POST /orders/{id}/close` (`{note}`), `GET /machines/board`.

### Frontend
- **Producción** page (replaces the phase-1b placeholder).
- **Detalle de orden**: new tab **Máquinas**; editable Checklist and Materiales tabs; actions **Asignar caducidad**, **Asignar máquinas**, **Cerrar orden**; difference display.
- **Máquinas** board; **Inicio** summary (today's orders by status, machines).

## Tests
- Operator role: cannot be created; existing operator cannot log in; PIN login endpoint gone; permission matrix for three roles.
- Split must add up exactly: 70 + 30 = 100 accepted; 70 + 20 rejected; 70 + 40 rejected (BR-7).
- Order cannot reach `assigned` without expiry; cannot start without being `assigned` (BR-20).
- Retrabajo expiry locked (previous order: copied; own stock: locked after first entry).
- Editing products/liters of an `assigned` order deletes assignments and returns to `created` (BR-16).
- Only one running/paused assignment per machine; queue order respected (BR-14).
- Pause/resume per machine; derived order status: one machine running + one paused → *En proceso*; both paused → *Pausada*; one completed + one paused → *Pausada* (BR-23).
- Completion stock movements with several base products, rounding to 2 decimals without losing liters across assignments (BR-8); negative stock allowed + alert (BR-9); remaining reservations released at completion (BR-10).
- Difference and tolerance highlighting (BR-12); closing allowed regardless; only `orders.close` can close; closed is read-only except comments (BR-11).
- Traceability fields record who and when; admin can fill them (BR-24).
- Cancel refused once production started (BR-17).

## Acceptance scenarios
1. Order `T-1 ANB` (100 L) appears in *Por asignar*. The Production manager enters expiry 03/2029 and assigns 70 L to M01 and 30 L to M04 → *Asignada*; trying 70 + 20 is refused.
2. From Producción, the Production manager starts M01; then pauses it (end of shift) → order *Pausada* (M04 not started). Next day resumes M01 and starts M04 → *En proceso*.
3. M01 is finished with 70 L and M04 with 29 L → *Completada*, *Faltante 1.00 L*; stock moves (base −99 L, finished +99 L, packaging), 1 L reservation released; the order appears in *Por cerrar*.
4. The Production manager fills the checklist, lote posterior and actual materials, then closes the order → *Cerrada*; an admin can still add a comment.
5. Mixed order (600 L NB + 400 L ANB → 1,000 L), single machine, completed with 990 L → base products consumed 594 L and 396 L.
6. History shows every event with user, local time and source `manual`.
7. Trying to log in as a former operator user shows *"Los operadores no usan la plataforma."*

## Definition of done
- [ ] The whole paper process can be done in the system without PLCs.
- [ ] Scenarios pass manually and in automated tests.
- [ ] Tests pass; `docs/PROGRESS.md` updated.
