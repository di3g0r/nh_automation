# Phase 4 — PLC Database Interface

> Status: v2.1 — 2026-10-09 (replaces `phase-4-plc-api-simulator.md` and the former phase 5). Prerequisites: phases 0–3 done. Read `00-overview.md` and `01-data-model.md` (v2) first.
> Goal: the PLCs can read their pending assignments from the database and write their actions to it, and the system applies those actions as if the operator had pressed the buttons.

## Context

The owner's decision (CONTEXT §9): **we send nothing to the PLC.** Every X seconds each PLC queries the database for its pending orders, alerts the operator on the machine's own screen, and writes every action (start, progress, pause, completion, liters) back to the database. **Programming the PLCs is out of scope**; this phase builds and documents only our side of the interface.

Design principle: the PLC never touches business tables. It **reads a view** and **inserts into an inbox table**; the backend validates and applies each event through the same assignment service used by manual actions (phase 3). Stock, statuses and audit stay consistent, and a PLC bug cannot corrupt data.

## Scope

**In:** PLC database roles and credentials, the `plc_pending_assignments` and `plc_assignment_sources` views, the `plc_events` inbox with trigger, the event processor, the machine's last PLC contact, the database port configuration, the interface document for the PLC programmer, the handover checklist.
**Out:** PLC programming; PLC simulator; a PLC events troubleshooting page; offline/outage handling (OPEN-8: nothing is done); an HTTP gateway (only if the real PLC cannot connect to PostgreSQL — see the last section).

## Database objects (migration)

### Roles and credentials
- Group role `plc_machine` (NOLOGIN) with:
  - `SELECT` on `plc_pending_assignments` and `plc_assignment_sources`.
  - `INSERT` on `plc_events` (only columns `assignment_id, event, liters, seq, error_code, message, plc_timestamp`) and `USAGE` on its sequence.
  - **No** access to anything else.
- One login role per machine, e.g. `plc_m01`, member of `plc_machine`; the name is stored in `machines.plc_db_username`.
- The master admin (permission `machines.plc_credentials`) can **create** and **rotate** a machine's PLC login from the Máquinas catalog. The password is generated, **shown once**, never stored by the app. Creation/rotation is audited (without the password). Hide the unused phase-1 machine API key in the UI.
- If the app's DB user cannot create roles, use a small privileged script in `deploy/` instead; record the choice in DECISIONS.

### Views (each PLC sees only its own machine)
- `plc_pending_assignments`: assignments of the machine whose `plc_db_username = current_user`, in `assigned`, `in_progress` or `paused`, ordered by `queue_position`. Columns: `assignment_id`, `operation_number`, `queue_position`, `status`, `result_code`, `result_name`, `result_presentation`, `planned_liters`, `actual_liters`, `operator_name`, `comments`.
- `plc_assignment_sources`: each source product of those assignments: `assignment_id`, `position`, `source_code`, `source_name`, `liters` (that source's share: source liters × planned liters ÷ order result liters).
- Views are `security_barrier` and owned by the app user, so PLC roles need no rights on base tables.

### `plc_events` inbox
Columns per `01-data-model.md` §2.2. A `BEFORE INSERT` trigger:
- sets `machine_id` from `current_user` (rejects the insert if the user is not linked to an active machine);
- sets `received_at = now()`; forces `processed_at`, `result`, `reject_reason` to null;
- validates `event` against the allowed list and `liters ≥ 0`;
- updates `machines.last_seen_at`.
- `NOTIFY plc_events` after insert so the processor reacts immediately.

## Event processor

- Runs inside the backend (background task in the `api` container); record the choice in DECISIONS. Wakes on `LISTEN plc_events` and also polls every 5 s as a fallback.
- Processes unprocessed events **in `received_at` order per machine**, each in its own transaction; sets `processed_at` and `result`.
- Mapping (actor = the machine, `source="plc"`):
  - `start` → start the assignment (must be the machine's first in queue and `assigned`).
  - `progress` → set `actual_liters` if greater than the current value (never decreases).
  - `pause` / `resume` → pause / resume.
  - `complete` → complete with `liters` as final actual liters; same stock movements as manual completion (BR-8).
  - `error` → `assignment_events` row of type `error` with code and message; shown on the machine board and in the order history; no status change.
- Duplicate (machine, seq) → `duplicate`, not applied (BR-13). Invalid for the current state → `rejected` with a reason code (`NOT_ON_MACHINE`, `INVALID_TRANSITION`, `NOT_FIRST_IN_QUEUE`, `BAD_PAYLOAD`). Rejected events are logged at warning level and keep their reason in `plc_events`, where a developer or the IT person can query them.
- Completion by the PLC does not require the checklist and actual packaging first; the operator fills them afterwards in the operator station, and the order cannot be **verified** until both are filled.
- Manual and PLC actions can coexist (e.g. the operator completes manually if the PLC fails); the last source is recorded. Events for completed or cancelled assignments are rejected.

## Web app changes
- Máquinas catalog: *Credenciales PLC* section (create/rotate login, username, last contact).
- Machine board: *Último contacto del PLC* (local time, "hace X min") and the latest PLC error.
- Order history and assignment detail show PLC events with source `plc`.

## Network and deployment
- Prod compose publishes PostgreSQL's port on the server. `pg_hba.conf` allows `plc_*` roles only from `PLC_ALLOWED_NETWORKS` (env) with `scram-sha-256`; the app user only from the Docker network. Document the firewall rule for the IT person.
- PLC roles get `CONNECTION LIMIT 3` and a `statement_timeout`.

## Document for the PLC programmer
`docs/PLC_INTERFACE.md`, in **Spanish**, self-contained:
- Connection data (host, port, database, auth method; per-machine user/password delivered separately).
- Recommended loop: every N seconds read `plc_pending_assignments` → if the first row is `assigned`, alert the operator → when the operator starts, insert `start` → insert `progress` every 5–10 s with cumulative liters → `pause`/`resume` as needed → `complete` with final liters.
- Column lists, allowed events, example `SELECT` and `INSERT` statements, the meaning of `seq` and why liters are cumulative, what happens to duplicates and rejected events.
- Questions for the PLC programmer (see handover checklist).

## Handover checklist (coordination, not development)
- [ ] Confirm with the PLC programmer: PLC brand/model (OPEN-6); **can it connect to PostgreSQL directly?**; machine IP addresses; polling interval; whether it can keep a persistent `seq` counter.
- [ ] Create each machine's PLC login and deliver credentials + `docs/PLC_INTERFACE.md`.
- [ ] With the IT person: open the database port only to the PLC addresses.
- [ ] First machine: watch its first real orders (machine board, order history, `plc_events.result`), compare PLC liters with a physical measurement, then roll out to the other machines.

## If the PLC cannot connect to PostgreSQL
Many PLCs only make HTTP requests. **Build this only if the handover confirms it is needed:** a minimal HTTP gateway (`GET /plc/v1/pending`, `POST /plc/v1/events`) that authenticates the machine and reads the same views / inserts into the same inbox, so the processor and rules stay identical. Update `PLC_INTERFACE.md` accordingly.

## Tests
Run against real PostgreSQL, inserting events while logged in as test PLC roles (no simulator needed):
- A PLC role reads only its own machine's rows and cannot `SELECT`/`UPDATE`/`DELETE` any business table.
- The trigger sets `machine_id` from the user; a PLC cannot insert events for another machine's assignment (rejected by the processor).
- Processor: happy path; duplicates; out-of-order progress doesn't decrease liters; `start` on a non-first assignment rejected; PLC completion produces exactly the same stock movements as manual completion.

## Acceptance scenarios
1. Order (1,000 L) split 500 L on M01 and 500 L on M02. Logged in as `plc_m01` and `plc_m02`, each sees only its own assignment; inserting `start`, `progress` and `complete` (500 L and 495 L) makes the order *Completada* with *Faltante 5.00 L*; stock moves as in phase 3.
2. Inserting the same event twice (same `seq`) doesn't change totals.
3. `plc_m01` running `SELECT * FROM work_orders` fails.
4. After a PLC `start`, the operator completes the assignment manually; history shows `plc` and `manual` events.

## Definition of done
- [ ] Scenarios pass on the dev stack with real PostgreSQL.
- [ ] `docs/PLC_INTERFACE.md` ready to hand to the PLC programmer.
- [ ] Tests pass; `docs/PROGRESS.md` updated. (The handover checklist is done later, with the PLC programmer.)
