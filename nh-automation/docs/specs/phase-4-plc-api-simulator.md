# Phase 4 — PLC API and Simulator

> Prerequisites: phases 0–3 done. Read `00-overview.md` and `01-data-model.md` first.
> Goal: machines receive assignments and report production through the API; a simulator proves it end to end before the real PLC is known.

## Scope

**In:** `/plc/v1` endpoints, machine API key auth, event processing, duplicate handling, offline detection, simulator, protocol document for the PLC programmer.
**Out:** adapting to the real PLC model (phase 5).

## Tables

`plc_events` (unique `machine_id, seq`). Uses `machines.api_key_hash`, `machines.last_seen_at`.

## Protocol [PROPOSED — OPEN-6, OPEN-7]

PLC HTTP clients are limited, so: **the PLC polls**, payloads are small flat JSON, plain HTTP on the isolated machine network, integers for booleans.

### Authentication
Header `X-API-Key: <machine key>`. Fallback `?key=` query parameter, enabled only by setting `plc_allow_query_key` (default off). Invalid key → 401 `{"ok":0,"error":"AUTH"}`. Requests only accepted from `PLC_ALLOWED_NETWORKS` (env).

### `GET /plc/v1/assignment`
Returns the machine's first assignment in queue (status assigned, in_progress or paused):
```json
{"has_job": 1, "assignment_id": 1532, "order": "8292 ANB",
 "product": "QVR200C1XL20F003", "liters": 500.00, "status": "assigned"}
```
or `{"has_job": 0}`. Each call updates `last_seen_at` (heartbeat).

### `POST /plc/v1/events`
```json
{"seq": 88021, "assignment_id": 1532, "event": "progress", "liters": 412.5, "ts": "2026-10-06T10:15:00"}
```
- `event`: `start`, `progress`, `pause`, `resume`, `complete`, `error`.
- `seq`: increasing per machine; already-seen seq → stored as duplicate, not applied, response `{"ok":1,"dup":1}` (BR-13).
- `liters`: **cumulative** total for the assignment (not delta).
- `error` adds `error_code` (int) and optional `message`; shows on the machine board and order history; does not change status.
- `ts` optional; without offset it is local time (NFR-7a). Server receive time is authoritative.
- Responses: `{"ok":1}` or `{"ok":0,"error":"<CODE>"}` with codes `NOT_ACTIVE` (assignment not on this machine / not startable), `INVALID_EVENT`, `INVALID_TRANSITION`, `BAD_PAYLOAD`.

### `POST /plc/v1/heartbeat`
Optional `{"state": <int>}` for idle machines; updates `last_seen_at`.

### Event processing
- Every request stored raw in `plc_events` (`applied` true/false).
- `start/pause/resume/complete` call the **same assignment service functions** as manual controls with `source="plc"`, actor = machine.
- `progress` updates `assignments.actual_liters` (only increases are applied).
- `complete` with `liters` = final actual liters; triggers completion stock movements (BR-8). Checklist/materials still filled by the operator on the station; completion from PLC is allowed before that, and the order cannot be verified until checklist and materials are filled.
- Manual and PLC sources can coexist; the last source is recorded.

### Offline detection (FR-PLC-6)
Machine is *Sin conexión* if `now − last_seen_at > plc_offline_seconds` (60). Shown on the machine board and operator station; operator can then use manual controls.

### Network failure [OPEN-8]
PLC keeps working, stores pending events, resends in order when the connection returns; cumulative liters + seq make this safe.

## Simulator (`tools/plc_simulator.py`)
- CLI: `--machines M01,M02 --keys-file keys.json --server http://... --flow-rate 2.0 --poll 3`.
- Polls, starts jobs, sends progress every N seconds at the flow rate, completes at planned liters.
- Flags to simulate: `--short 5` / `--excess 5` liters, `--pause-at 50%`, `--error-at 30%`, `--drop-network 20s`, `--duplicate-rate 0.1`, `--out-of-order`.
- Runs as a container in dev compose (`profiles: [sim]`).

## Documentation
`docs/PLC_PROTOCOL.md` (in Spanish and English), written for the person who programs the PLC: endpoints, examples, required sequence, retry rules, a checklist of PLC capabilities to confirm (HTTP client, JSON, custom headers, persistent counter for seq).

## Tests
- Auth, network restriction.
- Full happy path via API calls; duplicate seq ignored; out-of-order progress doesn't decrease liters.
- PLC complete → stock movements identical to manual completion.
- Offline detection.
- Simulator integration test: 2 machines, short fill → *Faltante*.

## Acceptance scenarios
1. Simulator runs M01 to 500 L and M02 to 495 L on order `8292 ANB`; order *Completada* with *Faltante 5.00 L*; stock moves as in phase 3.
2. Duplicated events don't change totals.
3. Stopping the simulator → machine shows *Sin conexión* after 60 s; operator completes manually; history shows `plc` and `manual` events.

## Definition of done
- [ ] Scenarios pass.
- [ ] `docs/PLC_PROTOCOL.md` ready to hand to the PLC programmer.
- [ ] Tests pass; `docs/PROGRESS.md` updated.
