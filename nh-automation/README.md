# Work Order and Production Tracking System

Internal system for ECOINDUSTRIAL PACÍFICO: digital work orders, inventory
with reservations, machine assignment, and a database interface for the PLCs. See
`docs/CONTEXT.md` and `docs/specs/` for the full specification.

This README covers phase 0 (foundation). It will grow with each phase.

## Stack

- **Backend**: Python 3.12, FastAPI, SQLAlchemy 2, Alembic, PostgreSQL 16.
- **Frontend**: React + TypeScript + Vite, Mantine, TanStack Query.
- **Web server**: Caddy (serves the frontend, proxies `/api`).
- **Containers**: Docker Compose (`deploy/docker-compose.dev.yml`, `deploy/docker-compose.prod.yml`).

## Repository structure

```
/backend      FastAPI app (app/), Alembic migrations/, tests/
/frontend     React app (src/)
/tools        samples/ (example import files)
/deploy       docker-compose files, Caddyfile, backup scripts, postgres/ (pg_hba for the PLCs)
/docs         CONTEXT.md, specs/, DECISIONS.md, PROGRESS.md, PLC_INTERFACE.md
```

## Network access

The system is reachable **only from the local network** (office and plant
LAN). There is no VPN and nothing is exposed to the internet. From phase 4 the
PostgreSQL port is opened only to the PLCs' addresses (see "PLC database
access").

## First-time setup

1. `cp .env.example .env` and fill in real values (DB password, `SECRET_KEY`, etc.).
2. Start the dev stack: `docker compose -f deploy/docker-compose.dev.yml up --build`
   - `db`: PostgreSQL. `api`: FastAPI with hot reload on `http://localhost:8000`.
     `web`: Vite dev server on `http://localhost:5173`.
   - The API runs Alembic migrations automatically on start.
3. Create the first master admin:
   ```
   docker compose -f deploy/docker-compose.dev.yml exec api python -m app.cli create-master-admin
   ```
4. Open `http://localhost:5173` and log in.

## Commands

### Dev stack (Docker)

| Action | Command |
|---|---|
| Start | `docker compose -f deploy/docker-compose.dev.yml up --build` |
| Stop | `docker compose -f deploy/docker-compose.dev.yml down` |
| Logs | `docker compose -f deploy/docker-compose.dev.yml logs -f api` |
| Create master admin | `docker compose -f deploy/docker-compose.dev.yml exec api python -m app.cli create-master-admin` |
| Seed default settings | `docker compose -f deploy/docker-compose.dev.yml exec api python -m app.cli seed-settings` |
| Seed dev data (dev only: sample products and clients, M01–M06, one user per role: master admin, admin, jefe de producción, operador) | `docker compose -f deploy/docker-compose.dev.yml exec api python -m app.cli seed-dev` |
| Re-ensure base catalogs (site, razones sociales, order sequences, 14 packaging items) | `docker compose -f deploy/docker-compose.dev.yml exec api python -m app.cli seed-catalogs` |
| Preview a catalog import from the external DB (add `--apply --username <u>` to save) | `docker compose -f deploy/docker-compose.dev.yml exec api python -m app.cli import-catalog products` |
| New migration | `docker compose -f deploy/docker-compose.dev.yml exec api alembic revision --autogenerate -m "message"` |
| Apply migrations | `docker compose -f deploy/docker-compose.dev.yml exec api alembic upgrade head` |

### Prod stack (Docker)

| Action | Command |
|---|---|
| Start | `docker compose -f deploy/docker-compose.prod.yml up -d --build` |
| Stop | `docker compose -f deploy/docker-compose.prod.yml down` |
| Manual backup | `docker compose -f deploy/docker-compose.prod.yml exec backup /usr/local/bin/backup.sh` |
| Restore a dump | `./deploy/restore.sh deploy/backups/<file>.sql.gz` |
| Update | backup → `git pull` → `docker compose -f deploy/docker-compose.prod.yml up -d --build` |

### Backend, without Docker (for local development/tests)

Requires Python 3.12 and a running PostgreSQL (e.g. `docker compose -f deploy/docker-compose.dev.yml up db`).

```
cd backend
python -m venv .venv && .venv/Scripts/activate   # or source .venv/bin/activate on Linux/macOS
pip install -r requirements-dev.txt
pytest                      # tests (uses an in-memory SQLite DB, see tests/conftest.py)
# Postgres-only tests (row locks, PLC roles/views/trigger): an EMPTY scratch DB
# TEST_POSTGRES_URL=postgresql+psycopg://nh_app:change-me@localhost:5432/nh_scratch pytest
ruff check app tests        # lint
mypy app                    # type check
alembic upgrade head        # apply migrations (needs DATABASE_URL pointing at Postgres)
python -m app.cli create-master-admin
uvicorn app.main:app --reload
```

### Frontend, without Docker

```
cd frontend
npm install
npm run dev          # Vite dev server, http://localhost:5173
npm run build         # type-check + production build
npm run test          # Vitest
npm run lint          # ESLint
npm run typecheck     # tsc --noEmit
```

## PLC database access (phase 4)

Each machine's PLC logs into PostgreSQL with its own user (`plc_m01`, …),
reads its pending orders from views and inserts its actions into
`plc_events`; the api container applies them within seconds. The interface for
the PLC programmer is `docs/PLC_INTERFACE.md` (Spanish).

- **Credentials:** the master admin creates or rotates a machine's login in
  *Catálogos → Máquinas → Credenciales PLC*. The password is shown once.
- **Prod network:** `docker-compose.prod.yml` publishes PostgreSQL on
  `PLC_DB_PORT` (default 5432). At start, `deploy/postgres/pg-hba-entrypoint.sh`
  writes `pg_hba.conf`: PLC users are accepted only from `PLC_ALLOWED_NETWORKS`
  (comma-separated CIDRs, e.g. `192.168.50.21/32,192.168.50.22/32`), the app
  and backup users only from the Docker network `DOCKER_SUBNET`
  (default `172.28.0.0/16`), everything else is rejected. Changing
  `PLC_ALLOWED_NETWORKS` needs `docker compose … up -d db` (recreate).
- **Firewall (IT):** also allow the port only from the PLC addresses. Docker
  bypasses `ufw` for published ports, so use the `DOCKER-USER` chain, e.g.:

  ```
  iptables -I DOCKER-USER -p tcp --dport 5432 -j DROP
  iptables -I DOCKER-USER -p tcp --dport 5432 -s 192.168.50.0/24 -j ACCEPT
  ```

  (make it persistent, e.g. with `iptables-persistent`). Set `PLC_DB_HOST` to
  the server's LAN address so the credentials dialog shows it.
- **Troubleshooting:** rejected PLC events keep their reason in the database:
  `SELECT id, machine_id, assignment_id, event, received_at, reject_reason
  FROM plc_events WHERE result = 'rejected' ORDER BY id DESC LIMIT 50;`
  (`docker compose -f deploy/docker-compose.prod.yml exec db psql -U <user> <db>`).
  They are also logged by the api container at warning level.
- The migration creates the group role `plc_machine`; the app's database user
  must be able to create roles (the image's `POSTGRES_USER` is a superuser).

## External catalog database

The real product/packaging inventory lives in another database whose
structure isn't known yet. Imports (UI: Catálogos → Productos / Materiales de
empaque → Importar) can read it once IT sets `EXTERNAL_CATALOG_DB_URL` and
writes two SELECT files. See `backend/external_sources/README.md`. CSV/XLSX
upload keeps working as a fallback (samples in `tools/samples/`).

## Backups

- `backup` service runs `deploy/backup.sh` nightly (02:00 local time), dumping
  to `deploy/backups/` and deleting dumps older than `BACKUP_RETENTION_DAYS`
  (default 30).
- Restore: `./deploy/restore.sh deploy/backups/<file>.sql.gz` (drops and
  recreates the database -- see the script's warning).
- Copy `deploy/backups/` off the server regularly (NFR-5); this repo does not
  automate off-server storage.

## Time zone

All timestamps are stored in UTC and shown in **America/Mazatlan (UTC-7, no
DST)**. `TZ=America/Mazatlan` is set on every container; backend helpers live
in `backend/app/core/timezone.py`.
