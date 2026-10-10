# 00 — Overview, Architecture and Conventions

> Status: v2 — 2026-10-09 (v1: 2026-10-06). Shared by every phase. Read `docs/CONTEXT.md` first.
> v2 changes: razones sociales, supervisor can cancel, PLC talks to the database (no PLC HTTP API), no VPN, backups kept but optional, open items updated.
> v2.1: phase 4 slimmed down (no simulator, no troubleshooting page); phase 5 removed and merged into phase 4's handover checklist.

## 1. Document map

| File | Content | Status |
|---|---|---|
| `00-overview.md` | This file: stack, architecture, roles, conventions, UI rules, non-functional requirements, deployment, open items | |
| `01-data-model.md` | Tables, statuses, business rules — the single source of truth for the database | |
| `phase-0-foundation.md` | Repo, Docker, database, auth, users, audit log, UI shell | Done |
| `phase-1-catalogs-inventory.md` | Products, packaging, clients, sites, machines, imports, stock | Done |
| `phase-1b-v2-updates.md` | Apply the v2 decisions to code already built (razones sociales, permissions, settings) | **Next** |
| `phase-2-work-orders.md` | Work orders (several source products), reservations, overselling block, printing | |
| `phase-3-assignments-operator.md` | Assignments, machine board, operator station, completion, verification | |
| `phase-4-plc-database-interface.md` | Database views and event table the PLCs use; event processing; document and handover checklist for the PLC programmer | |
| `phase-6-dashboard.md` | Production dashboard | |

`phase-4-plc-api-simulator.md` and `phase-5-real-plc.md` are obsolete and can be deleted. There is no phase 5; the dashboard keeps the number 6.

Conventions: requirement IDs (`FR-*`, `NFR-*`, `BR-*`) are stable and can be referenced in commits and tests. **[OPEN-n]** = undecided (see §10). **[PROPOSED]** = technical choice the owner may still change.

## 2. Technology stack [PROPOSED]

| Layer | Choice |
|---|---|
| Database | PostgreSQL |
| Backend / API | Python + FastAPI, SQLAlchemy 2, Alembic, Pydantic |
| Frontend | React + TypeScript + Vite, Mantine (component library), TanStack Query |
| Web server | Caddy (serves frontend, proxies API, internal HTTPS) |
| Containers | Docker + Docker Compose |
| Tests | pytest (backend), Vitest + Testing Library (frontend), Playwright (optional end-to-end) |

Use current stable versions.

## 3. Architecture

```
 Office PCs ───────(LAN)──┐
                          ▼
 Operator devices ─(LAN)──► Caddy (HTTPS) ──► Frontend (static React build)
                                  │
                                  └──► API (FastAPI) ──► PostgreSQL ◄──(restricted DB login)── PLCs (≈6)
                                                             ▲           reads pending orders,
                                       Event processor ──────┘           writes action events
 Backup job ──► nightly database dump (optional, kept)
```

- **Web app**: office screens and the operator station (same app, role-based views).
- **API** (`/api/v1`): the only entry point for the web app; all business rules live here.
- **PLC database interface** (phase 4): each PLC logs into PostgreSQL with its own restricted user, **reads** its pending assignments from a view and **inserts** action events into an inbox table. It cannot read or change anything else.
- **Event processor** (phase 4): part of the backend; applies PLC events to assignments through the same service functions as manual actions, so business rules stay in one place.
- **PLC programming is out of scope**; we provide and document the interface (CONTEXT §9).
- **No VPN.** Everything is reachable only from the local network.

### Repository structure

```
/backend      app/ (api, models, schemas, services, core), migrations/, tests/, external_sources/
/frontend     src/ (pages, components, api, i18n, utils)
/tools        samples/
/deploy       docker-compose files, Caddyfile, backup scripts, PLC DB role scripts
/docs         CONTEXT.md, specs/, DECISIONS.md, PROGRESS.md, PLC_INTERFACE.md, operations guide
CLAUDE.md
```

## 4. Roles and permissions

Roles: **master_admin** (director), **admin** (office), **supervisor** (warehouse) **[OPEN-10]**, **operator** (machines).

| Permission | Master admin | Admin | Supervisor | Operator |
|---|---|---|---|---|
| `users.manage` | ✅ | ❌ | ❌ | ❌ |
| `catalogs.manage` (products, packaging, razones sociales, clients, sites, machines) | ✅ | ✅ | ❌ | ❌ |
| `sequences.manage` (next operation number per razón social) | ✅ | ❌ | ❌ | ❌ |
| `inventory.view` | ✅ | ✅ | ✅ | ❌ |
| `inventory.move` (receipts, adjustments) | ✅ | ✅ | ✅ | ❌ |
| `orders.view` | ✅ | ✅ | ✅ | ❌ (only own assignments) |
| `orders.edit` (create/edit/delete) | ✅ | ✅ | ❌ | ❌ |
| `orders.approve` | ✅ | ✅ | ❌ | ❌ |
| `orders.assign` | ✅ | ✅ | ✅ | ❌ |
| `orders.traceability` (lot, expiry) | ✅ | ✅ | ✅ | ❌ |
| `orders.verify` | ✅ | ❌ | ✅ | ❌ |
| `orders.cancel` (cancel before start, close short after) | ✅ | ✅ | ✅ | ❌ |
| `assignments.work_own` (start/pause/complete manually, checklist, materials) | ✅ | ✅ | ✅ | ✅ (own) |
| `machines.board` | ✅ | ✅ | ✅ | ❌ |
| `machines.plc_credentials` (create/rotate PLC database logins) | ✅ | ❌ | ❌ | ❌ |
| `audit.view`, `settings.manage` | ✅ | ❌ | ❌ | ❌ |

The role → permissions map lives in **one module**. Endpoints check permissions, not roles.

## 5. API conventions

- JSON, prefix `/api/v1`, session cookie (httpOnly, Secure, SameSite=Lax) + CSRF token header for state-changing requests.
- Error shape: `{"error": {"code": "INSUFFICIENT_STOCK", "message": "<Spanish text>", "details": {...}}}`.
- Lists: `?page=&page_size=&sort=`; response `{"items": [...], "total": n}`.
- Decimal quantities are sent as strings or numbers with 2 decimals; never floats in the database (use `NUMERIC`).
- OpenAPI docs enabled at `/api/docs` (admins only in production).
- `GET /health` returns API and database status.

## 6. UI conventions

- All text in Spanish, kept in one translation/strings module (no hard-coded text scattered in components).
- Dates `dd/mm/aaaa`, 24-hour time, America/Mazatlan. Liters as `1,000.00 L`.
- Office navigation: **Inicio, Órdenes, Máquinas, Inventario, Catálogos** (Productos, Materiales de empaque, Razones sociales, Clientes, Sitios, Máquinas), **Usuarios, Bitácora, Configuración**. Items hidden when the user lacks permission.
- Operators land on **Estación de operador** (touch-friendly, large buttons).
- Consistent color-coded status badges. Clear Spanish error messages from the API.
- Works on Chrome/Edge (PC) and Chrome on Android tablets; responsive down to 360 px width.

## 7. Non-functional requirements

- **NFR-1 Security:** Argon2 (or bcrypt) for passwords and PINs; HTTPS for browsers (Caddy internal CA); CSRF protection; permission checks on every endpoint; nothing exposed to the internet. PLC database logins are restricted to their interface (read their view, insert into the event table) and PostgreSQL accepts them only from the machines' IP addresses.
- **NFR-2 Network:** the system is reachable only from the local network. **No VPN.** The PostgreSQL port is opened only to the PLCs' addresses (phase 4).
- **NFR-3 Performance:** pages < 2 s on LAN; PLC view queries < 100 ms; PLC events applied within 5 s. Scale: ≈6 machines, tens of users, a few hundred orders/day.
- **NFR-4 Reliability:** containers restart automatically; persistent database volume; health checks. Server or network outages are not handled beyond that (no offline mode).
- **NFR-5 Backups:** the nightly dump built in phase 0 (30-day retention) is kept; it is not a formal requirement. Copying dumps off the server is recommended.
- **NFR-6 Auditability:** no hard deletes of business records except orders in *Creada*.
- **NFR-7 Localization:** UI in Spanish (es-MX).
- **NFR-7a Time zone:** America/Mazatlan (UTC−7, no DST). Store UTC; display local everywhere (screens, prints, exports, history, audit). "Today" and daily grouping use the local day. PLC timestamps without offset are local. Single setting `TZ=America/Mazatlan`.
- **NFR-8 Browsers:** current Chrome and Edge; Chrome on Android.
- **NFR-9 Maintainability:** typed code; linters/formatters (ruff, mypy, eslint, prettier); tests for every business rule in `01-data-model.md` §4; migrations only; README for the IT person.

## 8. Deployment

**Docker Compose services:** `db` (PostgreSQL, volume), `api` (FastAPI, runs migrations on start, runs the PLC event processor from phase 4), `web` (Caddy: frontend + proxy to `/api`), `backup` (nightly `pg_dump`).

Two configurations: `docker-compose.dev.yml` (hot reload, seed data) and `docker-compose.prod.yml`. From phase 4, prod publishes the PostgreSQL port on the server, restricted by `pg_hba.conf` and the firewall to the PLC addresses (`PLC_ALLOWED_NETWORKS`).

Configuration via `.env` (`.env.example` committed): DB password, secret key, `PLC_ALLOWED_NETWORKS`, `TZ`, backup path, external catalog DB URL.

Server: Linux (e.g. Ubuntu Server LTS) with Docker; 4+ cores, 8+ GB RAM, SSD, UPS recommended. Update: backup → `git pull` → `docker compose up -d --build`.

## 9. Out of scope for v1

PLC programming; VPN; offline/outage handling; client management beyond name; sales, invoicing, accounting; label printer integration (until OPEN-12); multi-language UI; internet access.

## 10. Open items

Numbering matches `CONTEXT.md` §13. Implement the default; mark code with `TODO(OPEN-n)`.

| # | Item | Status / default |
|---|---|---|
| OPEN-1 | Meaning of *Retrabajo* | **Resolved:** two kinds (previous order / own stock) |
| OPEN-2 | Operation number generation | **Resolved:** separate sequence per razón social + its code |
| OPEN-3 | "Reen #" codes | Open — kept in free-text comments |
| OPEN-4 | Lot format; expiry display format | Open — free text lot; expiry stored as a date, shown `MM/AAAA`. Expiry rules resolved |
| OPEN-5 | Product code structure | Open — free text, unique |
| OPEN-6 | PLC brand/model | Open — only to confirm direct DB access vs a small HTTP gateway |
| OPEN-7 | System → PLC mechanism | **Resolved:** PLC polls the database |
| OPEN-8 | Server down during production | **Resolved:** nothing is done |
| OPEN-9 | Operator device | Open — responsive web, tablet-first |
| OPEN-10 | Supervisor role | Open — separate role |
| OPEN-11 | Cancellation rules | **Resolved:** all except operators; only before *En proceso* |
| OPEN-12 | Label/barcode printing | Open — printable order with barcode |
| OPEN-13 | VPN | **Resolved:** no VPN, LAN only |
| OPEN-14 | Other sites | Open — stock per site; one default site |
| OPEN-15 | Volume and users | Open — ≈6 machines, a few hundred orders/day |
| OPEN-16 | Razones sociales 3 and 4 | Open — placeholders `RS3`, `RS4` |
| OPEN-17 | Current operation numbers | Open — each sequence's next number is editable by the master admin |
| OPEN-18 | External catalog DB | Open — structure, access, one-time import vs ongoing sync |
