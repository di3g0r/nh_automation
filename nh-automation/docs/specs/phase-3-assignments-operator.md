# Phase 3 — Production Manager, Machines, Operator Station and Closing

> Status: v3 — 2026-10-13. Prerequisites: phases 0–2 done. Read `00-overview.md` and `01-data-model.md` (v3) first.
> Goal: the full process runs without paper and **without PLCs**: the Production manager completes and assigns new orders to machines → production runs (with pauses) using manual controls → completion moves stock → the Production manager closes the order.

## Scope

**In:** Production manager screen (Producción), expiry entry, machine assignment and split, machine queues, machine board, operator station with manual controls and pause/resume, traceability (lots, checklist, actual materials), completion with stock movements, differences, closing.
**Out:** the PLC database interface (phase 4). Design the assignment service so phase 4's event processor can call the same functions with `source="plc"` and a machine (instead of a user) as the actor.

## Tables

`assignments`, `assignment_events`.

## Requirements

### Producción (Production manager's home)
- **FR-PM-1** Two main lists:
  - **Por asignar**: orders in `created` (all of them, newest first), with what is missing: *Falta fecha de caducidad*, *Falta asignar máquinas*.
  - **Por cerrar**: orders in `completed`, with ordered vs actual liters and the difference highlighted when outside the acceptable range (BR-12).
- Also visible: orders `assigned`, `in_progress` and `paused` (with per-machine progress).
- Auto-refresh every 10 s.

### Expiry (BR-20)
- **FR-PM-2** Users with `orders.expiry` (Production manager, master admin) enter the expiry (month/year picker, shown `MM/AAAA`).
- Trabajo: editable until production starts. Retrabajo de orden anterior: already copied and locked. Retrabajo de inventario propio: entered once, then locked (confirm dialog: *"La fecha de caducidad de un retrabajo no se podrá cambiar."*).
- Who and when are recorded.

### Machine assignment (BR-7, BR-14)
- **FR-ASG-1** Users with `orders.assign` assign a `created` order to **one or more machines** (typically 1 or 2), each with planned liters.
- The form shows each machine's state (Libre, Ocupada, En pausa, Mantenimiento) and queue length, and a running total: *Asignado 70.00 / 100.00 L — faltan 30.00 L*. Save is only allowed when the total equals the order's finished liters exactly.
- One assignment per machine per order. Inactive/maintenance machines cannot be chosen. Assigning to a busy machine is allowed (it queues) with a notice.
- When the expiry is set **and** the assignments add up, the order becomes `assigned` (BR-6 transitions). Removing assignments or clearing a Trabajo expiry returns it to `created`.
- **FR-ASG-2** Before production starts, assignments can be changed (machines, liters) or removed. Once any assignment of the order has started, assignments are locked.
- **FR-ASG-3** Each machine has a queue by `queue_position`; users with `orders.assign` can reorder pending assignments on a machine. Only the first pending assignment of a machine can start, and only when no other assignment on that machine is running or paused (BR-14).
- No operator is assigned: the operator is whoever works the machine.
- **BR-16 reminder:** if an admin edits base products, liters or finished product of an `assigned` order, the assignments are deleted and the order returns to *Por asignar*.

### Operator station (FR-OPS)
- **FR-OPS-1** Touch-friendly (min 48 px targets, large text), tablet-first **[OPEN-9]**.
- **FR-OPS-2** The operator **selects the machine** they are working at (remembered on that device; changeable). Shows that machine's queue: operation number and type badge, Producto base → Producto terminado, planned liters, comments, packaging plan, expiry.
- **FR-OPS-3** Current assignment: status, planned vs actual liters, elapsed running time (excluding pauses); refresh every 5 s.
- **FR-OPS-4** Buttons (`production.control`, source `manual`): **Iniciar**, **Pausar**, **Reanudar**, **Terminar** (enter actual liters). In phase 4 the PLC normally does this and the operator's alert comes from the machine's own screen; the buttons remain as fallback, and **Pausar/Reanudar** remain the normal way for an operator to pause at the end of a shift.
- **FR-OPS-5** Traceability on the station (any user, recorded): checklist items, lot posterior, actual packaging and labels used (prefilled with planned values).

### Pause and resume (BR-23)
- Pausing an assignment keeps its liters and reservations; the order shows **Pausada** when none of its machines is running (derived, §3 of the data model). Each machine pauses independently.
- Who can pause/resume: any user with `production.control` (operator, Production manager, admin, master admin) and, in phase 4, the PLC. Normally the operator or the PLC.
- A paused assignment resumes on the same machine **[OPEN-20]**.

### Completion (BR-8, BR-9, BR-10, BR-12)
- Completing an assignment with actual liters A, in one transaction: finished product +A; each base product −(its liters × A ÷ order finished liters); packaging −actual quantities; reservations reduced.
- When every assignment is completed, the order becomes `completed` and remaining reservations are released (BR-10). It appears in **Por cerrar**.
- Difference shown as *Faltante* / *Excedente*, highlighted only when outside the range (`difference_tolerance_liters` or `difference_tolerance_percent`) **[OPEN-19]**.

### Closing (BR-11)
- Users with `orders.close` (Production manager, master admin) review a completed order: ordered vs actual liters, difference, per-machine results, checklist, lots, materials, comments. **Cerrar orden** with an optional note → `closed`.
- Closing is allowed even if the difference is outside the range or the checklist/lot are incomplete; in that case the dialog lists what is missing and asks for confirmation. (The owner said: if the Production manager approves it, it is approved.)
- Closed orders are read-only except comments.

### Machine board (FR-MCH)
- **FR-MCH-1** Card per machine: state (Libre, Ocupada, En pausa, Mantenimiento), current order + type, liters progress bar, queue length. (*Último contacto del PLC* is added in phase 4.)
- **FR-MCH-2** Master admin, admin, Production manager; auto-refresh 5 s. Users with `catalogs.manage` can toggle maintenance.

### API endpoints
`GET /production/to-assign`, `GET /production/to-close`, `PUT /orders/{id}/expiry`, `PUT /orders/{id}/assignments` (replace the full split: `[{machine_id, planned_liters}]`), `PATCH /assignments/{id}/queue-position`, `GET /machines/{id}/queue`, `POST /assignments/{id}/start|pause|resume|complete`, `PATCH /orders/{id}/checklist`, `PATCH /orders/{id}/traceability` (lots), `PATCH /assignments/{id}/materials`, `POST /orders/{id}/close` (`{note}`), `GET /machines/board`.

### Frontend
- **Producción** page (Production manager home; also visible to master admin).
- **Detalle de orden**: new tab **Máquinas** (assignments, per-machine status and liters); actions **Asignar caducidad**, **Asignar máquinas**, **Cerrar orden**; difference display.
- **Máquinas** board; **Inicio** summary (today's orders by status, machines).
- **Estación de operador** (machine selection, queue, current assignment, buttons, traceability).

## Tests
- Split must add up exactly: 70 + 30 = 100 accepted; 70 + 20 rejected; 70 + 40 rejected (BR-7).
- Order cannot reach `assigned` without expiry; cannot start without being `assigned` (BR-20).
- Retrabajo expiry locked (previous order: copied; own stock: locked after first entry).
- Editing products/liters of an `assigned` order deletes assignments and returns to `created` (BR-16).
- Only one running/paused assignment per machine; queue order respected (BR-14).
- Pause/resume per machine; derived order status: one machine running + one paused → *En proceso*; both paused → *Pausada*; one completed + one paused → *Pausada* (BR-23).
- Completion stock movements with several base products, rounding to 2 decimals without losing liters across assignments (BR-8); negative stock allowed + alert (BR-9); remaining reservations released at completion (BR-10).
- Difference and tolerance highlighting (BR-12); closing allowed regardless; only `orders.close` can close; closed is read-only except comments (BR-11).
- Traceability fields record who and when; an operator can fill them (BR-24).
- Cancel refused once production started (BR-17).

## Acceptance scenarios
1. Order `T-1 ANB` (100 L) appears in *Por asignar*. The Production manager enters expiry 03/2029 and assigns 70 L to M01 and 30 L to M04 → *Asignada*; trying 70 + 20 is refused.
2. The operator at M01 starts; at the end of the shift pauses → order *Pausada* (M04 not started). Next day resumes on M01 and the M04 operator starts → *En proceso*.
3. M01 completes with 70 L, M04 with 29 L → *Completada*, *Faltante 1.00 L*; stock moves (base −99 L, finished +99 L, packaging), 1 L reservation released; the order appears in *Por cerrar*.
4. The Production manager closes it (difference within range, or confirms if outside) → *Cerrada*; an admin can still add a comment.
5. Mixed order (600 L NB + 400 L ANB → 1,000 L), single machine, completed with 990 L → base products consumed 594 L and 396 L.
6. History shows every event with user, local time and source `manual`.

## Definition of done
- [ ] The whole paper process can be done in the system with manual controls.
- [ ] Scenarios pass manually and in automated tests.
- [ ] Tests pass; `docs/PROGRESS.md` updated.
