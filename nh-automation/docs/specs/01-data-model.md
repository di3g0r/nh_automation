# 01 — Data Model and Business Rules

> Status: v3 — 2026-10-13 (v2: 2026-10-09, v1: 2026-10-06). Shared by every phase. Each phase creates only the tables it needs (noted per table), via Alembic migrations.
> v3 changes: role `production_manager` replaces `supervisor`; base/finished product naming; `order_sequences` (Trabajo/Retrabajo) replaces per-razón-social numbering; new lifecycle (no approval, *paused*, *closed*); assignments to machines without an operator; expiry set by the Production manager; `order_comments`.

## 1. General rules

- Every table has `id` (integer PK), `created_at`, `updated_at` (timestamptz, UTC).
- Liters: `NUMERIC(12,2)`. Packaging units are whole numbers (stored in the same `NUMERIC(12,2)` stock columns, enforced as integers by the stock service — see DECISIONS 2026-10-09). Never floats.
- Business records are not hard-deleted; use `is_active` or a status (exception: orders in *Creada*).
- Columns ending in `_by` reference `users`; every user action records who and when.
- Derived values (available stock, difference, machine state) are computed, not stored, unless performance requires it.
- Naming: **base product** = *Producto base* (formerly ANTES/source); **finished product** = *Producto terminado* (formerly DESPUÉS/result). Use these names in code, database and API; never "source/result".

## 2. Tables

| Table | Phase | Columns |
|---|---|---|
| `users` | 0 (+1b) | username (unique), full_name, role (`master_admin`, `admin`, `production_manager`, `operator`), password_hash, pin_hash (nullable), is_active, failed_attempts, locked_until, last_login_at |
| `sessions` | 0 | user_id, token_hash, csrf_token, user_agent, expires_at, last_seen_at, revoked_at (infrastructure) |
| `audit_log` | 0 | user_id (nullable for system/PLC), entity, entity_id, action, before (JSONB), after (JSONB), created_at |
| `settings` | 0 | key (unique), value (JSONB) |
| `sites` | 1 | name (unique), is_default, is_active |
| `clients` | 1 | name, code (unique), is_active |
| `razones_sociales` | 1b | code (unique, e.g. `NB`, `ANB`; operation number suffix), name, is_active |
| `order_sequences` | 1b | order_type (`trabajo`, `retrabajo`; unique), prefix (`T`, `R`), next_number (integer ≥ 1, starts at 1) |
| `products` | 1 (+1b) | code (unique), name, provider, presentation (text: `1X20`, `1000`), container_liters (nullable), **razon_social_id** (FK, nullable in DB for imported rows; required in forms and to be used in an order), is_active |
| `packaging_items` | 1 | code (unique), description, category (`envase`, `caja`, `bolsa`, `etiqueta`, `otro`), low_stock_threshold, is_active |
| `machines` | 1 (+4) | code (unique), name, site_id, is_active, in_maintenance, api_key_hash (phase-1 artifact, unused), plc_db_username (nullable, phase 4), last_seen_at (nullable) |
| `stock_levels` | 1 | site_id, product_id **xor** packaging_item_id, on_hand; unique (site, item) |
| `stock_movements` | 1 | site_id, product_id xor packaging_item_id, type (`receipt`, `adjustment`, `consumption`, `production`), quantity (signed), order_id, assignment_id, user_id, note |
| `reservations` | 2 | order_id, site_id, product_id xor packaging_item_id, quantity, status (`active`, `consumed`, `released`) |
| `work_orders` | 2 | see §2.1 |
| `order_base_products` | 2 | order_id, position, product_id, `code`, `name`, `provider`, `presentation`, `razon_social_code` (snapshots), liters (> 0); unique (order_id, product_id) |
| `order_packaging` | 2 | order_id, packaging_item_id, planned_qty, actual_qty (nullable), actual_by, actual_at |
| `order_checklist` | 2 | order_id, item (`lote_etiqueta`, `niveles_producto`, `cantidades`, `embalaje`), checked, checked_by, checked_at |
| `order_comments` | 2 | order_id, user_id, text, created_at. Append-only; any time, any status |
| `assignments` | 3 | order_id, machine_id, planned_liters, actual_liters (nullable), status (`pending`, `running`, `paused`, `completed`, `cancelled`), queue_position, last_source (`plc`, `manual`), assigned_by, assigned_at, started_at, completed_at. **No operator column** — the operator is whoever works the machine |
| `assignment_events` | 3 | assignment_id, event (`assign`, `start`, `pause`, `resume`, `progress`, `complete`, `cancel`, `error`), liters, source (`plc`, `manual`), user_id (manual) or machine_id (PLC), created_at |
| `plc_events` | 4 | see §2.2 (inbox written by PLCs) |

### 2.1 `work_orders`

| Column | Notes |
|---|---|
| order_type | `trabajo` or `retrabajo`. Set at creation (the *Retrabajo* checkbox) and **immutable** |
| sequence | Integer taken from `order_sequences.next_number` for the order type (row-locked, then incremented) |
| operation_number | Unique, read-only: `<prefix>-<sequence> <razón social code>`, e.g. `T-447 NB`, `R-12 ANB` |
| rework_kind | Null for `trabajo`; `previous_order` or `own_stock` for `retrabajo` |
| related_order_id | FK to work_orders. Required when rework_kind = `previous_order`; null otherwise |
| client_id | Required, except null when rework_kind = `own_stock` |
| razon_social_id | Required (BR-22). Fixed after creation (the number contains it) |
| site_id, order_date | |
| finished_product_id + `finished_code`, `finished_name`, `finished_provider`, `finished_presentation` | *Producto terminado*, snapshot copied at save time |
| finished_liters | NUMERIC; defaults to the sum of base product liters |
| barcode_mode | `per_container`, `per_box` |
| labels_planned, labels_actual (+ labels_actual_by/at) | Integer |
| previous_lot, new_lot (+ new_lot_by/at) | Text **[OPEN-4]** |
| expiry_date (+ expiry_set_by/at) | DATE (1st of the month; shown `MM/AAAA` **[OPEN-4]**). Null until the Production manager sets it (BR-20) |
| status | `created`, `assigned`, `in_progress`, `paused`, `completed`, `closed`, `cancelled` |
| warnings | JSONB (e.g. packaging shortages at creation) |
| created_by; closed_by/at + close_note; cancelled_by/at + cancel_reason | |

Base products live in `order_base_products`; comments live in `order_comments` (the comment typed in the creation form becomes the first entry).

### 2.2 PLC interface (phase 4)

**`plc_events`** — inbox the PLCs insert into; the backend processes it.

| Column | Written by | Notes |
|---|---|---|
| machine_id | DB trigger | Set from the logged-in PLC user (`current_user` → `machines.plc_db_username`); the PLC cannot choose it |
| assignment_id | PLC | |
| event | PLC | `start`, `progress`, `pause`, `resume`, `complete`, `error` |
| liters | PLC | **Cumulative** liters for the assignment (not a delta) |
| seq | PLC (optional) | Increasing per machine; unique (machine_id, seq) when present |
| error_code, message | PLC | For `error` |
| plc_timestamp | PLC (optional) | Local time if no offset |
| received_at | DB default | Authoritative time |
| processed_at, result (`applied`, `duplicate`, `rejected`), reject_reason | Backend | |

**Views** (read-only for PLC users; each PLC sees only its own machine via `current_user`):
- `plc_pending_assignments`: assignment_id, operation_number, order_type, queue_position, status, finished product code/name/presentation, planned_liters, actual_liters, expiry_date, comments (latest first, joined).
- `plc_assignment_base_products`: assignment_id, position, base product code/name, liters (that product's share for the assignment).

Only assignments of orders with an expiry date appear (BR-20).

## 3. Statuses

**Order** (Spanish labels in UI):

| Value | Label | Reached when |
|---|---|---|
| `created` | Creada | Saved by admin or Production manager; stock reserved |
| `assigned` | Asignada | Expiry date set **and** machine assignments add up exactly to the order liters (BR-7) |
| `in_progress` | En proceso | At least one assignment `running` |
| `paused` | Pausada | Production started, no assignment `running`, at least one `paused` or `pending`, not all completed |
| `completed` | Completada | All non-cancelled assignments `completed` |
| `closed` | Cerrada | Production manager approved it |
| `cancelled` | Cancelada | Cancelled with reason before production started; reservations released |

Order status after `assigned` is **derived** from its assignments (recomputed in the same transaction as any assignment change).

Allowed order transitions:
```
created → assigned            (expiry set + assignments add up)
assigned → created            (products/quantities edited, assignments removed, or expiry cleared)
assigned → in_progress        (first assignment starts)
in_progress ⇄ paused
in_progress | paused → completed
completed → closed            (Production manager)
created | assigned → cancelled
```

**Assignment:** `pending → running ⇄ paused → completed`; `pending → cancelled` (only while the order has not started).

## 4. Business rules (each needs automated tests)

| # | Rule |
|---|---|
| BR-1 | **Available = on hand − sum of active reservations**, per item and site. |
| BR-2 | Creating or editing an order fails with `INSUFFICIENT_STOCK` if, for **any** base product, available < its liters (excluding the order's own reservations when editing). Details list each short product with on hand, reserved, available and the orders holding reservations. |
| BR-3 | Reservation checks and writes happen in one transaction with row locks on the stock rows involved (locked in a fixed order, e.g. by stock row id, to avoid deadlocks); concurrent requests cannot over-reserve. |
| BR-4 | Packaging shortage at creation is a **warning** stored on the order, not a block. |
| BR-5 | Every stock change writes a `stock_movements` row; `stock_levels.on_hand` is only updated together with a movement. |
| BR-6 | Only transitions in §3 are allowed; others return `INVALID_TRANSITION`. |
| BR-7 | **Machine split:** the planned liters of the order's non-cancelled assignments must add up **exactly** to `finished_liters` (e.g. 100 L = 70 L on M01 + 30 L on M04). Each assignment > 0; one assignment per machine per order; inactive or in-maintenance machines cannot be used. Assignments can be changed only before production starts. |
| BR-8 | On assignment completion with actual liters A: finished product +A (`production`); each base product −(its liters × A ÷ order finished liters) (`consumption`, proportional **[PROPOSED]**); packaging −actual quantities entered (`consumption`); matching reservations reduced and marked `consumed` when exhausted. |
| BR-9 | Consumption is recorded even if on-hand goes negative; negative stock raises an alert. |
| BR-10 | Cancellation and order completion release all remaining active reservations (`released`). |
| BR-11 | **Closing:** only `completed` orders can be closed, by a user with `orders.close`. The difference (BR-12) is shown and highlighted if outside the acceptable range **[OPEN-19]**, but never blocks closing. Optional close note. Closed orders are read-only except for comments. |
| BR-12 | Difference = actual finished liters (sum of assignments) − ordered finished liters. Negative = *Faltante*, positive = *Excedente*. Within range if \|difference\| ≤ `difference_tolerance_liters` **or** ≤ `difference_tolerance_percent` % of the ordered liters. |
| BR-13 | PLC events are processed in `received_at` order per machine. An event with an already seen (machine, seq) → `duplicate`; an event invalid for the assignment's state → `rejected` with reason. Progress never decreases actual liters. |
| BR-14 | Only one assignment per machine is `running` or `paused` at a time; others queue by `queue_position`. A paused assignment resumes on the same machine **[OPEN-20]**. |
| BR-15 | At least one active master admin must exist. |
| BR-16 | **Editing:** while the order is `created` or `assigned` (nothing started), users with `orders.edit` can edit any field except order type and razón social, as many times as needed. Changing base products, liters or the finished product of an `assigned` order deletes its assignments and returns it to `created` (the Production manager reassigns). Once any assignment has started, only comments, lots, checklist and actual materials can change. |
| BR-17 | Orders can be deleted only in `created`; cancelled only in `created` or `assigned`, with a mandatory reason, by users with `orders.cancel` (never operators). |
| BR-18 | Every create/update/delete and domain action writes `audit_log` with before/after values. |
| BR-19 | **Operation number:** the `order_sequences` row of the order type is locked, `sequence = next_number`, then `next_number + 1`, in the order-creation transaction. Trabajo and Retrabajo have independent sequences shared by all razones sociales. Numbers are never reused (a deleted order leaves a gap). |
| BR-20 | **Expiry:** null at creation; set by a user with `orders.expiry`. *Retrabajo* `previous_order` → copied from the related order at creation and **locked**. *Retrabajo* `own_stock` → entered once, then **locked**. *Trabajo* → editable until production starts. No automatic default. An order cannot reach `assigned` (and so cannot start) without an expiry date. |
| BR-21 | **Order type** is chosen at creation and immutable. Rework kinds: `previous_order` requires `related_order_id` (an order in `completed` or `closed`) and a client (defaults to the related order's client); `own_stock` has no client and no related order. |
| BR-22 | **Razón social:** each base product must have a razón social. If all base products share one, it is used automatically; otherwise the user must choose one of theirs. |
| BR-23 | **Pause/resume:** any user with `production.control` (normally the operator) or the PLC can pause or resume a running/paused assignment. Pausing never releases reservations or stock. |
| BR-24 | **Traceability authorship:** lots, checklist items, actual packaging and labels can be filled by any user with `orders.traceability`; each records who and when. |

## 5. Seed data

- Site: ECOINDUSTRIAL PACÍFICO (default).
- Razones sociales: `NB` NOBELTECH, `ANB` AGRONB, `RS3` "Razón social 3 (por definir)", `RS4` "Razón social 4 (por definir)" **[OPEN-16]**.
- Order sequences: `trabajo` prefix `T`, next 1; `retrabajo` prefix `R`, next 1.
- Clients: none in production (NOBELTECH/AGRONB were seeded as clients in phase 1 by mistake; phase 1b deactivates them).
- Packaging items (14): ENVCO01005 Envase 1 L liso Novapack; ENVLI01004 Envase 1 L corrugado; ENVLI20001 Envase 20 L Fisher; ENVLI05003 Envase 5 L Fisher; ENVLI25007 Envase 250 ml liso Novapack; ENVCO25006 Envase 250 ml corrugado; BOLTE20008 Bolsa termosellada 1 kg; CAJ01FP007 Caja Forcrop 12x1; CAJ05FP006 Caja Forcrop 4x5; CAJ01BL003 Caja blanca 12x1; CAJ05BL004 Caja blanca 4x5; CAJ05BL005 Caja blanca 0.250 grs; CAJ01AZ002 Caja azul 12x1; CAJ05AZ001 Caja azul 4x5.
- Dev only: products GRN100C1XL20F004 (NB-NEEM, GRN, 1X20, razón social NB), QVR200C1XL09M01 (BASE CALCIO, QVR, 1000, ANB), QVR200C1XL20F003 (NH-CALCIO, QVR, 1X20, ANB); two sample clients; machines M01–M06; one user per role.
