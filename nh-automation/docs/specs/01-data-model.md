# 01 — Data Model and Business Rules

> Status: Draft v1 — 2026-10-06. Shared by every phase. Each phase creates only the tables it needs (noted per table), via Alembic migrations.

## 1. General rules

- Every table has `id` (integer PK), `created_at`, `updated_at` (timestamptz, UTC).
- Liters: `NUMERIC(12,2)`. Packaging units: `INTEGER`. Never floats.
- Business records are not hard-deleted; use `is_active` or a status (exception: orders in *Creada*).
- Foreign keys to users record *who*: `created_by`, `approved_by`, etc.
- Derived values (available stock, difference, machine state) are computed, not stored, unless performance requires it.

## 2. Tables

| Table | Phase | Columns |
|---|---|---|
| `users` | 0 | username (unique), full_name, role (`master_admin`, `admin`, `supervisor`, `operator`), password_hash, pin_hash (nullable), is_active, failed_attempts, locked_until, last_login_at |
| `audit_log` | 0 | user_id (nullable for system/PLC), entity, entity_id, action (`create`, `update`, `delete`, or a domain action like `approve`), before (JSONB), after (JSONB), created_at |
| `settings` | 0 | key (unique), value (JSONB) |
| `sites` | 1 | name (unique), is_default, is_active |
| `clients` | 1 | name, code (unique, e.g. `NB`, `ANB`), is_active |
| `products` | 1 | code (unique), name, provider, presentation (text: `1X20`, `1000`), container_liters (nullable), is_active |
| `packaging_items` | 1 | code (unique), description, category (`envase`, `caja`, `bolsa`, `etiqueta`, `otro`), low_stock_threshold, is_active |
| `machines` | 1 | code (unique), name, site_id, is_active, in_maintenance, api_key_hash (nullable), last_seen_at (nullable) |
| `stock_levels` | 1 | site_id, product_id **xor** packaging_item_id, on_hand; unique (site, item) |
| `stock_movements` | 1 | site_id, product_id xor packaging_item_id, type (`receipt`, `adjustment`, `consumption`, `production`), quantity (signed), order_id, assignment_id, user_id, note |
| `reservations` | 2 | order_id, site_id, product_id xor packaging_item_id, quantity, status (`active`, `consumed`, `released`) |
| `work_orders` | 2 | see §2.1 |
| `order_packaging` | 2 | order_id, packaging_item_id, planned_qty, actual_qty (nullable) |
| `order_checklist` | 2 | order_id, item (`lote_etiqueta`, `niveles_producto`, `cantidades`, `embalaje`), checked, checked_by, checked_at |
| `assignments` | 3 | order_id, machine_id, operator_id, queue_position, planned_liters, actual_liters (nullable), status, last_source (`plc`, `manual`), assigned_by, assigned_at, started_at, paused_at, completed_at |
| `assignment_events` | 3 | assignment_id, event (`assign`, `start`, `pause`, `resume`, `progress`, `complete`, `cancel`, `move`), liters, source (`plc`, `manual`), user_id, created_at |
| `plc_events` | 4 | machine_id, assignment_id, seq, event, liters, error_code, message, plc_timestamp, received_at, raw_payload (JSONB), applied; unique (machine_id, seq) |

### 2.1 `work_orders`

| Column | Notes |
|---|---|
| operation_number | Unique, read-only, e.g. `8292 ANB` **[OPEN-2]** |
| sequence | Integer from a global DB sequence |
| type | `trabajo`, `retrabajo` |
| related_order_id | Nullable FK to work_orders **[OPEN-1]** |
| client_id, site_id, order_date | |
| source_product_id + `source_code`, `source_name`, `source_provider`, `source_presentation` | Snapshot copied at save time |
| source_liters | NUMERIC |
| result_product_id + `result_code`, `result_name`, `result_provider`, `result_presentation` | Snapshot |
| result_liters | NUMERIC |
| comments | Text |
| barcode_mode | `per_container`, `per_box` |
| labels_planned, labels_actual | Integer |
| previous_lot, new_lot, expiry | Text **[OPEN-4]** |
| status | `created`, `approved`, `assigned`, `in_progress`, `completed`, `verified`, `cancelled` |
| warnings | JSONB (e.g. packaging shortages at creation) |
| created_by; approved_by/at; verified_by/at; cancelled_by/at + cancel_reason; closed_by/at + close_reason | |

## 3. Statuses

**Order** (Spanish labels in UI):

| Value | Label | Reached when |
|---|---|---|
| `created` | Creada | Saved; stock reserved |
| `approved` | Aprobada | Approved by admin/master admin |
| `assigned` | Asignada | Planned liters of active assignments = order liters |
| `in_progress` | En proceso | At least one assignment started |
| `completed` | Completada | All assignments completed, or closed short |
| `verified` | Verificada | Supervisor verified (needs new lot + expiry) |
| `cancelled` | Cancelada | Cancelled with reason; reservations released |

Allowed transitions:
```
created → approved → assigned → in_progress → completed → verified
approved → created            (when quantities/products are edited)
assigned → approved           (when assignments are cancelled and liters no longer covered)
created | approved | assigned → cancelled
in_progress → completed       (via close short)
```

**Assignment:** `assigned → in_progress ⇄ paused → completed`; `assigned → cancelled`.

## 4. Business rules (each needs automated tests)

| # | Rule |
|---|---|
| BR-1 | **Available = on hand − sum of active reservations**, per item and site. |
| BR-2 | Creating or editing an order fails with `INSUFFICIENT_STOCK` if source product available < source liters (excluding the order's own reservation when editing). The error details include on hand, reserved, available and the orders holding reservations. |
| BR-3 | Reservation checks and writes happen in one transaction with row locks (`SELECT … FOR UPDATE` on the stock_levels row); concurrent requests cannot over-reserve. |
| BR-4 | Packaging shortage at creation is a **warning** stored on the order, not a block. |
| BR-5 | Every stock change writes a `stock_movements` row; `stock_levels.on_hand` is only updated together with a movement. |
| BR-6 | Only transitions in §3 are allowed; others return `INVALID_TRANSITION`. |
| BR-7 | Sum of planned liters of non-cancelled assignments ≤ order source liters. |
| BR-8 | On assignment completion: source product −actual liters (`consumption`), result product +actual liters (`production`), packaging −actual quantities (`consumption`); matching reservation quantity reduced and marked `consumed` when exhausted. |
| BR-9 | Consumption is recorded even if on-hand goes negative; negative stock raises an alert. |
| BR-10 | Cancel and close-short release all remaining active reservations (`released`). |
| BR-11 | Verification requires `new_lot` and `expiry`; verified orders are read-only. |
| BR-12 | Difference = actual liters (sum of assignments) − ordered liters. Negative = *Faltante*, positive = *Excedente*. |
| BR-13 | PLC events with an already seen (machine_id, seq) are stored as duplicates and not applied. |
| BR-14 | Only one assignment per machine is `in_progress`/`paused` at a time; others queue by `queue_position`. |
| BR-15 | At least one active master admin must exist. |
| BR-16 | Order editing: *created* → all fields; *approved* → editing products/quantities returns it to *created*; *assigned* and later → only comments, lot, expiry, checklist. |
| BR-17 | Orders can be deleted only in *created* (reservations removed); otherwise cancelled with reason. |
| BR-18 | Every create/update/delete and domain action writes `audit_log` with before/after values. |

## 5. Seed data

- Site: ECOINDUSTRIAL PACÍFICO (default).
- Clients: NOBELTECH (`NB`), AGRONB (`ANB`).
- Packaging items (14): ENVCO01005 Envase 1 L liso Novapack; ENVLI01004 Envase 1 L corrugado; ENVLI20001 Envase 20 L Fisher; ENVLI05003 Envase 5 L Fisher; ENVLI25007 Envase 250 ml liso Novapack; ENVCO25006 Envase 250 ml corrugado; BOLTE20008 Bolsa termosellada 1 kg; CAJ01FP007 Caja Forcrop 12x1; CAJ05FP006 Caja Forcrop 4x5; CAJ01BL003 Caja blanca 12x1; CAJ05BL004 Caja blanca 4x5; CAJ05BL005 Caja blanca 0.250 grs; CAJ01AZ002 Caja azul 12x1; CAJ05AZ001 Caja azul 4x5.
- Dev only: products GRN100C1XL20F004 (NB-NEEM, GRN, 1X20), QVR200C1XL09M01 (BASE CALCIO, QVR, 1000), QVR200C1XL20F003 (NH-CALCIO, QVR, 1X20); machines M01–M06; one user per role.
