# Phase 3 — Assignments, Machine Board and Operator Station

> Prerequisites: phases 0–2 done. Read `00-overview.md` and `01-data-model.md` first.
> Goal: the full process runs without paper and **without PLCs**: assign → operator works manually → completion moves stock → supervisor verifies.

## Scope

**In:** assignments and queues, machine board, operator station with manual controls, checklist and actual materials, completion with stock movements, differences, partial fills / close short, verification.
**Out:** PLC endpoints (phase 4). Design the assignment service so phase 4 can call the same functions with `source="plc"`.

## Tables

`assignments`, `assignment_events`.

## Requirements

### Assignments (FR-ASG)
- **FR-ASG-1** Only *Aprobada* orders (or *Asignada* with liters still unassigned) can be assigned.
- **FR-ASG-2** Assign screen shows machine cards (state, current order, queue length) and an operator selector showing each operator's active assignments.
- **FR-ASG-3 / BR-14** Each machine has a queue (`queue_position`). Assigning to a busy machine allowed with a warning. Queue can be reordered (drag or up/down).
- **FR-ASG-4 / BR-7** Planned liters cannot exceed the order's unassigned liters. Default planned liters = remaining liters.
- **FR-ASG-5** Not-started assignments can be cancelled or moved to another machine/operator.
- Order status updates automatically: all liters assigned → *Asignada*; any assignment started → *En proceso*; all completed (or closed short) → *Completada*.
- Machines in maintenance or inactive cannot receive assignments.

### Operator station (FR-OPS)
- **FR-OPS-1** Touch-friendly (min 48 px targets, large text), tablet-first **[OPEN-9]**.
- **FR-OPS-2** *Mis órdenes*: operator's queue ordered by machine and position: operation number, ANTES → DESPUÉS, planned liters, comments, packaging plan.
- **FR-OPS-3** Current assignment view: status, planned vs actual liters, elapsed time; refresh every 5 s (FR-OPS-6).
- **FR-OPS-4** Before completing, operator must: fill the 4 checklist items and enter actual packaging and labels used (prefilled with planned values).
- **FR-OPS-5** Manual buttons **Iniciar**, **Pausar**, **Reanudar**, **Terminar** (enter actual liters). Recorded with `source="manual"`. Only the first assignment in a machine's queue can be started (BR-14).
- **FR-ASG-7/8** Every change writes `assignment_events` with user, time and source.

### Completion (BR-8, BR-9, BR-12)
- Completing an assignment, in one transaction: consumption of source product (actual liters), production of result product (actual liters), consumption of packaging (actual qty), reduce reservations.
- Packaging actuals are entered per assignment; order totals are sums.
- Order difference shown as *Faltante* / *Excedente* (highlight only if |difference| > `difference_tolerance_liters`).
- **FR-ASG-6 Partial fill:** if the order's completed liters < ordered and no assignments remain, admin chooses **Nueva asignación** for the remainder or **Cerrar con faltante** (mandatory reason → *Completada*, remaining reservations released, BR-10).

### Verification
- Supervisor/master admin sets **Lote posterior** and **Fecha de caducidad** (if missing) and clicks **Verificar** (BR-11). Order becomes read-only.
- The checklist can also be edited by the supervisor before verifying.

### Machine board (FR-MCH)
- **FR-MCH-1** Card per machine: state (Libre, Ocupada, En pausa, Mantenimiento; *Sin conexión* added in phase 4), current order + operator, liters progress bar, queue length.
- **FR-MCH-2** Admin, master admin, supervisor; auto-refresh 5 s. Admin can toggle maintenance.

### API endpoints
`POST /orders/{id}/assignments`, `PATCH /assignments/{id}` (move machine/operator, reorder), `POST /assignments/{id}/cancel`, `GET /assignments/mine`, `GET /assignments/{id}`, `POST /assignments/{id}/start|pause|resume|complete`, `PATCH /assignments/{id}/checklist`, `PATCH /assignments/{id}/materials`, `POST /orders/{id}/close-short` (`{reason}`), `POST /orders/{id}/verify`, `GET /machines/board`.

### Frontend
- **Detalle de orden**: new tab **Asignaciones**; buttons **Asignar**, **Cerrar con faltante**, **Verificar**; difference display.
- **Asignar** dialog/page.
- **Máquinas** board page; summary on **Inicio** (today's orders by status, machines).
- **Estación de operador**: Mis órdenes, current assignment, checklist, materials, manual buttons.

## Tests
- Split assignment 500 + 500; cannot exceed 1,000 (BR-7).
- Only one active assignment per machine (BR-14).
- Completion stock movements and reservation reduction (BR-8); negative stock allowed + alert (BR-9).
- Difference calculation (BR-12) and close short releasing reservations (BR-10).
- Verification requires lot + expiry; verified is read-only (BR-11).
- Operator sees only own assignments; cannot act on others' (403).
- Order status auto-transitions.

## Acceptance scenarios
1. Order `8292 ANB` (1,000 L) approved and split: 500 L on M01 (operator A), 500 L on M02 (operator B). Both machine cards show it.
2. Operator A completes manually with 500 L; operator B with 495 L. Order shows *Completada*, *Faltante 5.00 L*. Stock: BASE CALCIO −995 L, NH-CALCIO +995 L, packaging consumed; reservation released.
3. Supervisor cannot verify until new lot and expiry are entered; after verifying, the order is read-only.
4. History shows every event with user, local time and source `manual`.

## Definition of done
- [ ] The whole paper process can be done in the system with manual controls.
- [ ] Scenarios pass manually and in automated tests.
- [ ] Tests pass; `docs/PROGRESS.md` updated.
