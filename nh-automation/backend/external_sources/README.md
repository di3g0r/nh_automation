# External catalog database — query files

The real product / packaging inventory lives in an external database whose
structure is not known yet. The import screen (**Catálogos → Productos /
Materiales de empaque → Importar → Base de datos externa**) and the CLI
(`python -m app.cli import-catalog ...`) read it through two plain SELECTs
kept here, so adapting to the real schema is configuration, not code.

## Setup (when access to the real database is available)

1. **Driver.** Add the Python driver for that database to
   `backend/requirements.txt` and rebuild the `api` image. Examples:
   | Database | URL prefix | Package |
   |---|---|---|
   | SQL Server (e.g. CONTPAQi) | `mssql+pyodbc://` or `mssql+pymssql://` | `pyodbc` (+ ODBC driver in the image) / `pymssql` |
   | MySQL / MariaDB | `mysql+pymysql://` | `pymysql` |
   | PostgreSQL | `postgresql+psycopg://` | already installed |
   | Firebird (e.g. Aspel SAE) | `firebird+fdb://` | `sqlalchemy-firebird`, `fdb` |
   | SQLite file | `sqlite:///path/file.db` | built in |
2. **Connection.** Set `EXTERNAL_CATALOG_DB_URL` in `.env`. Use a
   **read-only** database user: the importer only runs SELECTs and always
   rolls back, but the account should not be able to write anyway.
3. **Queries.** Copy `products.sql.example` → `products.sql` and
   `packaging_items.sql.example` → `packaging_items.sql`, then edit them for
   the real tables. Each must be a single `SELECT` (or `WITH ... SELECT`).
   The file paths can be changed with `EXTERNAL_PRODUCTS_QUERY_FILE` /
   `EXTERNAL_PACKAGING_QUERY_FILE`.
4. **Try it.** Preview without saving:
   `docker compose -f deploy/docker-compose.dev.yml exec api python -m app.cli import-catalog products`

## Column contract

Alias the result columns to these names (Spanish or English, case and
accents ignored; full alias list in `app/services/imports/columns.py`):

| Products | Required | Packaging items | Required |
|---|---|---|---|
| `codigo` | yes | `codigo` | yes |
| `nombre` | yes | `descripcion` | yes |
| `proveedor` | yes | `categoria` (`envase`, `caja`, `bolsa`, `etiqueta`, `otro`) | yes |
| `presentacion` | yes | `umbral_stock_bajo` (whole number) | no |
| `litros_por_envase` | no | `existencia_inicial` (whole units) | no |
| `existencia_inicial` (liters) | no | | |

`existencia_inicial` is booked at the default site as a receipt
("Importación inicial"), only for items that have no stock movements yet.

If a plain SELECT is not enough (e.g. data spread over several databases, or
an API instead of a database), implement a new source class in
`app/services/imports/sources.py` (see the `ImportSource` protocol).
