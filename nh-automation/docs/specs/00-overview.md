# 00 — Overview, Architecture and Conventions

> Status: Draft v1 — 2026-10-06. Shared by every phase. Read `docs/CONTEXT.md` first.

## 1. Document map

| File | Content |
|---|---|
| `00-overview.md` | This file: stack, architecture, roles, conventions, UI rules, non-functional requirements, deployment, open items |
| `01-data-model.md` | Tables, statuses, business rules — the single source of truth for the database |
| `phase-0-foundation.md` | Repo, Docker, database, auth, users, audit log, UI shell |
| `phase-1-catalogs-inventory.md` | Products, packaging, clients, sites, machines, imports, stock |
| `phase-2-work-orders.md` | Work orders, reservations, overselling block, printing |
| `phase-3-assignments-operator.md` | Assignments, machine board, operator station, completion, verification |
| `phase-4-plc-api-simulator.md` | PLC endpoints and PLC simulator |
| `phase-5-real-plc.md` | Integration with the real PLC model |
| `phase-6-dashboard.md` | Production dashboard |

Conventions: requirement IDs (`FR-*`, `NFR-*`) are stable and can be referenced in commits and tests. **[OPEN-n]** = undecided (see §10). **[PROPOSED]** = technical choice the owner may still change.

## 2. Technology stack [PROPOSED]

| Layer | Choice |
|---|---|
| Database | PostgreSQL |
| Backend / API | Python + FastAPI, SQLAlchemy 2, Alembic, Pydantic |
| Frontend | React + TypeScript + Vite, Mantine (component library), TanStack Query |
| Web server | Caddy (serves frontend, proxies API, internal HTTPS) |
| Containers | Docker + Docker Compose |
| VPN | WireGuard |
| Tests | pytest (backend), Vitest + Testing Library (frontend), Playwright (optional end-to-end) |

Use current stable versions.

## 3. Architecture

```
 Office PCs ──(VPN / LAN)──┐
                           ▼
 Operator tablets ──(LAN)──► Caddy (HTTPS) ──► Frontend (static React build)
                                   │
                                   └──► API (FastAPI) ──► PostgreSQL
                                          ▲
 PLCs (≈6 machines) ──(HTTP, machine network)──┘
 Backup job ──► nightly database dump ──► external storage
```

- **Web app**: office screens and the operator station (same app, role-based views).
- **API** (`/api/v1`): the only entry point for the web app; all business rules live here.
- **PLC API** (`/plc/v1`): small, separate endpoints for limited PLC HTTP clients (phase 4).
- **PLC simulator**: script that behaves like a PLC (phase 4).

### Repository structure

```
/backend      app/ (api, models, schemas, services, core), migrations/, tests/
/frontend     src/ (pages, components, api, i18n, utils)
/tools        plc_simulator.py, import helpers
/deploy       docker-compose files, Caddyfile, backup scripts
/docs         CONTEXT.md, specs/, DECISIONS.md, PROGRESS.md, operations guide
CLAUDE.md
```

## 4. Roles and permissions

Roles: **master_admin** (director), **admin** (office), **supervisor** (warehouse) **[OPEN-10]**, **operator** (machines).

| Permission | Master admin | Admin | Supervisor | Operator |
|---|---|---|---|---|
| `users.manage` | ✅ | ❌ | ❌ | ❌ |
| `catalogs.manage` (products, packaging, clients, sites, machines) | ✅ | ✅ | ❌ | ❌ |
| `inventory.view` | ✅ | ✅ | ✅ | ❌ |
| `inventory.move` (receipts, adjustments) | ✅ | ✅ | ✅ | ❌ |
| `orders.view` | ✅ | ✅ | ✅ | ❌ (only own assignments) |
| `orders.edit` (create/edit/delete) | ✅ | ✅ | ❌ | ❌ |
| `orders.approve` | ✅ | ✅ | ❌ | ❌ |
| `orders.assign` | ✅ | ✅ | ✅ | ❌ |
| `orders.traceability` (lot, expiry) | ✅ | ✅ | ✅ | ❌ |
| `orders.verify` | ✅ | ❌ | ✅ | ❌ |
| `orders.cancel` | ✅ | ✅ | ❌ | ❌ |
| `assignments.work_own` (start/pause/complete, checklist, materials) | ✅ | ✅ | ✅ | ✅ (own) |
| `machines.board` | ✅ | ✅ | ✅ | ❌ |
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
- Office navigation: **Inicio, Órdenes, Máquinas, Inventario, Catálogos** (Productos, Materiales de empaque, Clientes, Sitios, Máquinas), **Usuarios, Bitácora, Configuración**. Items hidden when the user lacks permission.
- Operators land on **Estación de operador** (touch-friendly, large buttons).
- Consistent color-coded status badges. Clear Spanish error messages from the API.
- Works on Chrome/Edge (PC) and Chrome on Android tablets; responsive down to 360 px width.

## 7. Non-functional requirements

- **NFR-1 Security:** Argon2 (or bcrypt) for passwords and PINs; HTTPS for browsers (Caddy internal CA); CSRF protection; permission checks on every endpoint; machine API keys hashed; PLC endpoints only from the machine network; nothing exposed to the internet.
- **NFR-2 Network:** web app reachable only via VPN and the plant LAN **[OPEN-13]**; recommended separate VLAN for PLCs.
- **NFR-3 Performance:** pages < 2 s on LAN; PLC endpoints < 200 ms. Scale: ≈6 machines, tens of users, a few hundred orders/day.
- **NFR-4 Reliability:** containers restart automatically; persistent database volume; health checks.
- **NFR-5 Backups:** nightly dump, 30-day retention, copied off the server; documented and tested restore. UPS recommended.
- **NFR-6 Auditability:** no hard deletes of business records except orders in *Creada*.
- **NFR-7 Localization:** UI in Spanish (es-MX).
- **NFR-7a Time zone:** America/Mazatlan (UTC−7, no DST). Store UTC; display local everywhere (screens, prints, exports, history, audit). "Today" and daily grouping use the local day. PLC timestamps without offset are local. Single setting `TZ=America/Mazatlan`.
- **NFR-8 Browsers:** current Chrome and Edge; Chrome on Android.
- **NFR-9 Maintainability:** typed code; linters/formatters (ruff, mypy, eslint, prettier); tests for every business rule in `01-data-model.md` §4; migrations only; README for the IT person.

## 8. Deployment

**Docker Compose services:** `db` (PostgreSQL, volume, internal only), `api` (FastAPI, runs migrations on start), `web` (Caddy: frontend + proxy to `/api` and `/plc`), `backup` (scheduled `pg_dump` to a mounted folder).

Two configurations: `docker-compose.dev.yml` (hot reload, seed data, simulator) and `docker-compose.prod.yml`.

Configuration via `.env` (`.env.example` committed): DB password, secret key, allowed networks, `TZ`, backup path.

Server: Linux (e.g. Ubuntu Server LTS) with Docker; 4+ cores, 8+ GB RAM, SSD, UPS. VPN: WireGuard on the server or router (IT decides). Update: backup → `git pull` → `docker compose up -d --build`.

## 9. Out of scope for v1

Client management beyond name/code, sales, invoicing, accounting, label printer integration (until OPEN-12), multi-language UI, internet access outside the VPN.

## 10. Open items

Numbering matches `CONTEXT.md` §13. Implement the default; mark code with `TODO(OPEN-n)`.

| # | Item | Default until decided |
|---|---|---|
| OPEN-1 | Meaning of *Retrabajo* | Optional link to a related order |
| OPEN-2 | Operation number generation | Global sequence + client code (`8292 ANB`) |
| OPEN-3 | "Reen #" codes | Kept in free-text comments |
| OPEN-4 | Lot and expiry format | Free text, no validation |
| OPEN-5 | Product code structure | Free text, unique |
| OPEN-6 | PLC brand/model | Protocol in phase 4, validated with simulator |
| OPEN-7 | System → PLC mechanism | PLC polls the API |
| OPEN-8 | Server down during production | PLC resends on reconnection; manual fallback |
| OPEN-9 | Operator device | Responsive web, tablet-first |
| OPEN-10 | Supervisor role | Separate role |
| OPEN-11 | Cancellation rules | Cancel before *En proceso*; close short after |
| OPEN-12 | Label/barcode printing | Printable order with barcode |
| OPEN-13 | VPN purpose | VPN for office devices; separate machine network |
| OPEN-14 | Other sites | Stock per site; one default site |
| OPEN-15 | Volume and users | ≈6 machines, a few hundred orders/day |
