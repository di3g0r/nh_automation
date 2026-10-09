# CLAUDE.md — instructions for Claude Code

This repository is the **Work Order and Production Tracking System** for a liquid fertilizer plant (ECOINDUSTRIAL PACÍFICO). It replaces paper work orders, tracks inventory with reservations, assigns orders to machines and operators, and receives production data from machine PLCs.

## Read before working

1. `docs/CONTEXT.md` — the business, the paper form, glossary.
2. `docs/specs/00-overview.md` — stack, architecture, roles, conventions, non-functional requirements.
3. `docs/specs/01-data-model.md` — all tables and business rules (shared by every phase).
4. **Only the phase spec you were asked to implement** (`docs/specs/phase-N-*.md`).

Do not implement features from later phases. If the current phase needs something small from a later phase, add the minimum and note it.

## Working rules

- Build **one phase per session**. Start by reading the phase spec and writing a short plan; then implement; then run tests.
- A phase is done only when its "Definition of done" checklist passes, including tests.
- Code, database, API and comments in **English**. Everything the user sees in **Spanish (es-MX)**.
- Store timestamps in UTC; show everything in **America/Mazatlan (UTC−7, no DST)**. "Today" means the local day.
- Business rules live in the service layer (`backend/app/services`), never in route handlers.
- Every database change goes through an Alembic migration.
- Permissions are checked in the API with named permissions (see overview §4), never only in the UI.
- Items marked **[OPEN-n]** are undecided: implement the stated default, keep it easy to change, and add `TODO(OPEN-n)`.
- Do not invent business rules. If a spec is ambiguous, ask or pick the simplest option and record it in `docs/DECISIONS.md`.
- After finishing a phase, update `docs/PROGRESS.md` (what was built, deviations, known issues).

## Commands

Full reference in `README.md`. Quick list:

| Action | Command |
|---|---|
| Start dev stack | `docker compose -f deploy/docker-compose.dev.yml up --build` |
| Stop dev stack | `docker compose -f deploy/docker-compose.dev.yml down` |
| Start prod stack | `docker compose -f deploy/docker-compose.prod.yml up -d --build` |
| Create master admin | `docker compose -f deploy/docker-compose.dev.yml exec api python -m app.cli create-master-admin` |
| Seed default settings | `docker compose -f deploy/docker-compose.dev.yml exec api python -m app.cli seed-settings` |
| Seed dev data (dev only: sample products, M01–M06, one user per role) | `docker compose -f deploy/docker-compose.dev.yml exec api python -m app.cli seed-dev` |
| Re-ensure base catalogs (site, clients, 14 packaging items) | `docker compose -f deploy/docker-compose.dev.yml exec api python -m app.cli seed-catalogs` |
| Preview a catalog import from the external DB (add `--apply --username <u>` to save) | `docker compose -f deploy/docker-compose.dev.yml exec api python -m app.cli import-catalog products` |
| New migration | `docker compose -f deploy/docker-compose.dev.yml exec api alembic revision --autogenerate -m "message"` |
| Apply migrations | `docker compose -f deploy/docker-compose.dev.yml exec api alembic upgrade head` |
| Backend tests | `cd backend && pytest` (venv with `requirements-dev.txt`; uses in-memory SQLite, see `tests/conftest.py`) |
| Backend lint / types | `cd backend && ruff check app tests` / `mypy app` |
| Frontend tests | `cd frontend && npm run test` (Vitest) |
| Frontend lint / types / build | `cd frontend && npm run lint` / `npm run typecheck` / `npm run build` |
| Manual backup | `docker compose -f deploy/docker-compose.prod.yml exec backup /usr/local/bin/backup.sh` |
| Restore a backup | `./deploy/restore.sh deploy/backups/<file>.sql.gz` |
