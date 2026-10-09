# Work Order and Production Tracking System

Internal system for ECOINDUSTRIAL PACÍFICO: digital work orders, inventory
with reservations, machine/operator assignment, and PLC integration. See
`docs/CONTEXT.md` and `docs/specs/` for the full specification.

This README covers phase 0 (foundation). It will grow with each phase.

## Stack

- **Backend**: Python 3.12, FastAPI, SQLAlchemy 2, Alembic, PostgreSQL 16.
- **Frontend**: React + TypeScript + Vite, Mantine, TanStack Query.
- **Web server**: Caddy (serves the frontend, proxies `/api` and `/plc`).
- **Containers**: Docker Compose (`deploy/docker-compose.dev.yml`, `deploy/docker-compose.prod.yml`).

## Repository structure

```
/backend      FastAPI app (app/), Alembic migrations/, tests/
/frontend     React app (src/)
/tools        PLC simulator, import helpers (later phases)
/deploy       docker-compose files, Caddyfile, backup scripts
/docs         CONTEXT.md, specs/, DECISIONS.md, PROGRESS.md
```

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
