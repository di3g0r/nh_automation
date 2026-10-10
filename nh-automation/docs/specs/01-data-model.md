# 01 — Data Model and Business Rules

> Status: v2 — 2026-10-09 (v1: 2026-10-06). Shared by every phase. Each phase creates only the tables it needs (noted per table), via Alembic migrations.
> v2 changes: `razones_sociales` and per-razón-social sequences; `products.razon_social_id`; several source products per order (`order_sources`); rework kinds; expiry rules; PLC event inbox and views for direct database access.

## 1. General rules

- Every table has `id` (integer PK), `created_at`, `updated_at` (timestamptz, UTC).
- Liters: `NUMERIC(12,2)`. Packaging units are whole numbers (stored in the same `NUMERIC(12,2)` stock columns, enforced as integers by the stock service — see DECISIONS 2026-10-09). Never floats.
- Business records are not hard-deleted; use `is_active` or a status (exception: orders in *Creada*).
- Foreign keys to users record *who*: `created_by`, `approved_by`, etc.
- Derived values (available stock, difference, machine state) are computed, not stored, unless performance requires it.

## 2. Tables

| Table | Phase | Columns |
|---|---|---|
| `users` | 0 | username (unique), full_name, role (`master_admin`, `admin`, `supervisor`, `operator`), password_hash, pin_hash (nullable), is_active, failed_attempts, locked_until, last_login_at |
| `sessions` | 0 | user_id, token_hash, csrf_token, user_agent, expires_at, last_seen_at, revoked_at (infrastructure) |
| `audit_log` | 0 | user_id (nullable for system/PLC), entity, entity_id, action, before (JSONB), after (JSONB), created_at |
| `settings` | 0 | key (unique), value (JSONB) |
| `sites` | 1 | name (unique), is_default, is_active |
| `clients` | 1 | name, code (unique), is_active |
| `razones_sociales` | **1b** | code (unique, e.g. `NB`, `ANB`; used as the operation number suffix), name, next_number (integer ≥ 1), is_active |
| `products` | 1 (+1b) | code (unique), name, provider, presentation (text: `1X20`, `1000`), container_liters (nullable), **razon_social_id** (FK, nullable in DB for imported rows; required in forms and to be used in an order), is_active |
| `packaging_items` | 1 | code (unique), description, category (`envase`, `caja`, `bolsa`, `etiqueta`, `otro`), low_stock_threshold, is_active |
| `machines` | 1 (+4) | code (unique), name, site_id, is_active, in_maintenance, api_key_hash (phase-1 artifact; unused once phase 4 is built), **plc_db_username** (nullable, phase 4), last_seen_at (nullable) |
| `stock_levels` | 1 | site_id, product_id **xor** packaging_item_id, on_hand; unique (site, item) |
| `stock_movements` | 1 | site_id, product_id xor packaging_item_id, type (`receipt`, `adjustment`, `consumption`, `production`), quantity (signed), order_id, assignment_id, user_id, note |
| `reservations` | 2 | order_id, site_id, product_id xor packaging_item_id, quantity, status (`active`, `consumed`, `released`) |
| `work_orders` | 2 | see §2.1 |
| `order_sources` | 2 | order_id, position, product_id, `code`, `name`, `provider`, `presentation`, `razon_social_code` (snapshots), liters (> 0); unique (order_id, product_id) |
| `order_packaging` | 2 | order_id, packaging_item_id, planned_qty, actual_qty (nullable) |
| `order_checklist` | 2 | order_id, item (`lote_etiqueta`, `niveles_producto`, `cantidades`, `embalaje`), checked, checked_by, checked_at |
| `assignments` | 3 | order_id, machine_id, operator_id, queue_position, planned_liters, actual_liters (nullable), status, last_source (`plc`, `manual`), assigned_by, assigned_at, started_at, paused_at, completed_at |
| `assignment_events` | 3 | assignment_id, event (`assign`, `start`, `pause`, `resume`, `progress`, `complete`, `cancel`, `move`, `error`), liters, source (`plc`, `manual`), user_id, machine_id, created_at |
| `plc_events` | 4 | see §2.2 (inbox written by PLCs) |

### 2.1 `work_orders`

| Column | Notes |
|---|---|
| razon_social_id | Required. Default: the razón social shared by all source products; if they differ, the user must pick one of the source products' razones sociales |
| sequence | Integer taken from `razones_sociales.next_number` (row-locked, then incremented) |
| operation_number | Unique, read-only: `<sequence> <razón social code>`, e.g. `8292 ANB` |
| type | `trabajo`, `retrabajo` |
| rework_kind | Null for `trabajo`; `previous_order` or `own_stock` for `retrabajo` |
| related_order_id | FK to work_orders. Required when rework_kind = `previous_order`; null otherwise |
| client_id | Required, except null when rework_kind = `own_stock` |
| site_id, order_date | |
| result_product_id + `result_code`, `result_name`, `result_provider`, `result_presentation` | DESPUÉS, snapshot copied at save time |
| result_liters | NUMERIC; defaults to the sum of source liters |
| comments | Text |
| barcode_mode | `per_container`, `per_box` |
| labels_planned, labels_actual | Integer |
| previous_lot, new_lot | Text **[OPEN-4]** |
| expiry_date | DATE (day stored as 1st of the month; shown `MM/AAAA` **[OPEN-4]**). Rules in BR-20 |
| status | `created`, `approved`, `assigned`, `in_progress`, `completed`, `verified`, `cancelled` |
| warnings | JSONB (e.g. packaging shortages at creation) |
| created_by; approved_by/at; verified_by/at; cancelled_by/at + cancel_reason; closed_by/at + close_reason | |

Sources (ANTES) live in `order_sources`; there are **no** `source_*` columns on `work_orders`.

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
- `plc_pending_assignments`: assignment_id, operation_number, queue_position, status, result product code/name/presentation, planned_liters, actual_liters, operator name, comments.
- `plc_assignment_sources`: assignment_id, position, source product code/name, liters (planned share for that assignment).

## 3. Statuses

**Order** (Spanish labels in UI):

| Value | Label | Reached when |
|---|---|---|
| `created` | Creada | Saved; stock reserved |
| `approved` | Aprobada | Approved by admin/master admin |
| `assigned` | Asignada | Planned liters of active assignments = order result liters |
| `in_progress` | En proceso | At least one assignment started |
| `completed` | Completada | All assignments completed, or closed short |
| `verified` | Verificada | Supervisor verified (needs new lot + expiry) |
| `cancelled` | Cancelada | Cancelled with reason; reservations released |

Allowed transitions:
```
created → approved → assigned → in_progress → completed → verified
approved → created            (when products/quantities are edited)
assigned → approved           (when assignments are cancelled and liters no longer covered)
created | approved | assigned → cancelled
in_progress → completed       (via close short)
```

**Assignment:** `assigned → in_progress ⇄ paused → completed`; `assigned → cancelled`.

## 4. Business rules (each needs automated tests)

| # | Rule |
|---|---|
| BR-1 | **Available = on hand − sum of active reservations**, per item and site. |
| BR-2 | Creating or editing an order fails with `INSUFFICIENT_STOCK` if, for **any** source product, available < its source liters (excluding the order's own reservations when editing). Details list each short product with on hand, reserved, available and the orders holding reservations. |
| BR-3 | Reservation checks and writes happen in one transaction with row locks on the stock rows involved (locked in a fixed order, e.g. by stock row id, to avoid deadlocks); concurrent requests cannot over-reserve. |
| BR-4 | Packaging shortage at creation is a **warning** stored on the order, not a block. |
| BR-5 | Every stock change writes a `stock_movements` row; `stock_levels.on_hand` is only updated together with a movement. |
| BR-6 | Only transitions in §3 are allowed; others return `INVALID_TRANSITION`. |
| BR-7 | Sum of planned liters of non-cancelled assignments ≤ order **result** liters. |
| BR-8 | On assignment completion with actual liters A: result product +A (`production`); each source product −(its source liters × A ÷ order result liters) (`consumption`, proportional **[PROPOSED]**); packaging −actual quantities entered for that assignment (`consumption`); matching reservations reduced and marked `consumed` when exhausted. |
| BR-9 | Consumption is recorded even if on-hand goes negative; negative stock raises an alert. |
| BR-10 | Cancel, close-short and order completion release all remaining active reservations (`released`), e.g. the 5 L left reserved after a 995 L fill of a 1,000 L order. |
| BR-11 | Verification requires `new_lot` and `expiry_date`; verified orders are read-only. |
| BR-12 | Difference = actual result liters (sum of assignments) − ordered result liters. Negative = *Faltante*, positive = *Excedente*. |
| BR-13 | PLC events are processed in `received_at` order per machine. An event with an already seen (machine, seq) → `duplicate`; an event invalid for the assignment's state → `rejected` with reason. Progress never decreases actual liters. |
| BR-14 | Only one assignment per machine is `in_progress`/`paused` at a time; others queue by `queue_position`. |
| BR-15 | At least one active master admin must exist. |
| BR-16 | Order editing: *created* → all fields; *approved* → editing products/quantities returns it to *created*; *assigned* and later → only comments, lot, expiry, checklist. |
| BR-17 | Orders can be deleted only in *created* (reservations removed); otherwise cancelled with reason. Cancel is allowed only in *created*, *approved*, *assigned*; after that, close short. Operators can never cancel. |
| BR-18 | Every create/update/delete and domain action writes `audit_log` with before/after values. |
| BR-19 | **Operation number:** the order's razón social row is locked, `sequence = next_number`, then `next_number + 1`, in the order-creation transaction. Numbers are never reused (a deleted *created* order leaves a gap). The razón social is fixed once the order is created (changing it would change the number). |
| BR-20 | **Expiry:** *trabajo* → default `order_date + default_shelf_life_years` (setting, default 3), editable. *Retrabajo* `previous_order` → default copied from the related order, editable. *Retrabajo* `own_stock` → no default; the user enters the original expiry (required before approval). |
| BR-21 | **Rework kinds:** `previous_order` requires `related_order_id` (an order in *completed* or *verified*) and a client (defaults to the related order's client); `own_stock` has no client and no related order. |
| BR-22 | **Razón social:** each source product must have a razón social. If all sources share one, it is used automatically; otherwise the user must choose one of the sources' razones sociales. |

## 5. Seed data

- Site: ECOINDUSTRIAL PACÍFICO (default).
- Razones sociales: `NB` NOBELTECH, `ANB` AGRONB, `RS3` "Razón social 3 (por definir)", `RS4` "Razón social 4 (por definir)" **[OPEN-16]**; `next_number` = 1 **[OPEN-17]**.
- Clients: none in production (NOBELTECH/AGRONB were seeded as clients in phase 1 by mistake; phase 1b deactivates them).
- Packaging items (14): ENVCO01005 Envase 1 L liso Novapack; ENVLI01004 Envase 1 L corrugado; ENVLI20001 Envase 20 L Fisher; ENVLI05003 Envase 5 L Fisher; ENVLI25007 Envase 250 ml liso Novapack; ENVCO25006 Envase 250 ml corrugado; BOLTE20008 Bolsa termosellada 1 kg; CAJ01FP007 Caja Forcrop 12x1; CAJ05FP006 Caja Forcrop 4x5; CAJ01BL003 Caja blanca 12x1; CAJ05BL004 Caja blanca 4x5; CAJ05BL005 Caja blanca 0.250 grs; CAJ01AZ002 Caja azul 12x1; CAJ05AZ001 Caja azul 4x5.
- Dev only: products GRN100C1XL20F004 (NB-NEEM, GRN, 1X20, razón social NB), QVR200C1XL09M01 (BASE CALCIO, QVR, 1000, ANB), QVR200C1XL20F003 (NH-CALCIO, QVR, 1X20, ANB); two sample clients; machines M01–M06; one user per role.
