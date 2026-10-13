# Phase 6 — Production Dashboard

> Status: v3 — 2026-10-13. Prerequisites: phase 3 done (phase 4 recommended for real PLC data). Read `00-overview.md` and `01-data-model.md` first.
> Goal: daily production visible by machine, operator and product.

## Requirements
- **FR-DSH-1** Uses existing data only (assignments, assignment_events, work_orders, stock_movements). Add indexes or a reporting view if needed; no duplicated data.
- **FR-DSH-2** Dashboard page **Tablero de producción** (master admin, admin, Production manager):
  - Date range selector (default today; days are local UTC−7, NFR-7a).
  - KPI tiles: orders by status today, liters produced, orders completed, average fill time, total faltante/excedente.
  - Liters produced per machine (bar), per product (table), per razón social and per order type (Trabajo/Retrabajo). Per operator only where a user is recorded on manual actions (orders are assigned to machines, not operators).
  - Liters per day over the selected range (line).
  - Differences (faltante/excedente) per order/machine over time.
  - Machine utilization: time running vs paused vs idle per machine per day.
  - Time from *Creada* to *Asignada* and from *Completada* to *Cerrada* (Production manager response times).
- Filters: site, machine, operator, product, client, razón social, order type.
- Export to XLSX/CSV for any table.
- Auto-refresh every 60 s when viewing today.

## API
`GET /reports/summary`, `GET /reports/production?group_by=machine|operator|product|day`, `GET /reports/differences`, `GET /reports/utilization`, `GET /reports/export?...`.

## Tests
- Aggregations match seeded data; local-day boundaries (an assignment completed at 23:30 local counts for that local day).

## Definition of done
- [ ] Dashboard shows correct figures for seeded and real data.
- [ ] Exports open in Excel with Spanish headers.
- [ ] Tests pass; `docs/PROGRESS.md` updated.
