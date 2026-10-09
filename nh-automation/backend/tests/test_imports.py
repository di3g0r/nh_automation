"""Catalog import (FR-CAT-7): file and external-database sources, preview, confirm, modes."""

from __future__ import annotations

import io
import sqlite3
from decimal import Decimal

import pytest
from openpyxl import Workbook

from app.core.config import get_settings
from app.models.audit_log import AuditLog
from app.models.catalogs import PackagingItem, Product
from app.models.stock import StockLevel, StockMovement
from tests.conftest import login_as

API = "/api/v1/imports"

VALID_CSV = (
    "Código,Nombre,Proveedor,Presentación,Litros por envase,Existencia inicial\n"
    "GRN100C1XL20F004,NB-NEEM,GRN,1X20,20,400\n"
    "QVR200C1XL09M01,BASE CALCIO,QVR,1000,1000,\"2,500.50\"\n"
    "QVR200C1XL20F003,NH-CALCIO,QVR,1X20,,\n"
)

BAD_CSV = (
    "codigo;nombre;proveedor;presentacion;litros_por_envase\n"
    "A1;Uno;GRN;1X20;20\n"
    ";Sin código;GRN;1X20;20\n"  # missing required field
    "A1;Duplicado;GRN;1X20;20\n"  # duplicate code in file
    "A3;Tres;GRN;1X20;veinte\n"  # invalid number
)


def _post(client, headers, step, kind="products", *, content=None, filename="p.csv",
          mode="create_only", source="file"):
    files = {"file": (filename, content, "application/octet-stream")} if content else None
    return client.post(
        f"{API}/{kind}/{step}",
        data={"source": source, "mode": mode},
        files=files,
        headers=headers,
    )


def test_preview_valid_file_saves_nothing(client, db_session, base_catalogs):
    headers = login_as(client, db_session, "admin")
    resp = _post(client, headers, "preview", content=VALID_CSV.encode())
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["has_errors"] is False
    assert body["summary"]["create"] == 3
    assert body["summary"]["initial_stock"] == 2
    assert body["rows"][1]["values"]["initial_stock"] == "2500.50"
    assert db_session.query(Product).count() == 0


def test_confirm_valid_file(client, db_session, base_catalogs):
    headers = login_as(client, db_session, "admin")
    resp = _post(client, headers, "confirm", content=VALID_CSV.encode())
    assert resp.status_code == 200, resp.text

    products = {p.code: p for p in db_session.query(Product).all()}
    assert set(products) == {"GRN100C1XL20F004", "QVR200C1XL09M01", "QVR200C1XL20F003"}
    assert products["QVR200C1XL20F003"].container_liters is None
    assert Decimal(products["GRN100C1XL20F004"].container_liters) == Decimal("20")

    movements = db_session.query(StockMovement).all()
    assert len(movements) == 2
    assert {m.note for m in movements} == {"Importación inicial"}
    assert {m.type for m in movements} == {"receipt"}
    assert all(m.site_id == base_catalogs.id for m in movements)
    level = (
        db_session.query(StockLevel)
        .filter(StockLevel.product_id == products["QVR200C1XL09M01"].id)
        .one()
    )
    assert Decimal(level.on_hand) == Decimal("2500.50")

    entities = [a.entity for a in db_session.query(AuditLog).all()]
    assert entities.count("product") == 3
    assert entities.count("stock") == 2
    assert entities.count("import") == 1


def test_file_with_errors_shows_them_and_saves_nothing(client, db_session, base_catalogs):
    headers = login_as(client, db_session, "admin")
    preview = _post(client, headers, "preview", content=BAD_CSV.encode()).json()
    assert preview["has_errors"] is True
    by_row = {r["row_number"]: r for r in preview["rows"]}
    assert by_row[2]["action"] == "create"
    assert "Código: campo obligatorio." in by_row[3]["errors"]
    assert any("duplicado" in e for e in by_row[4]["errors"])
    assert any("no es un número válido" in e for e in by_row[5]["errors"])
    assert preview["summary"]["error"] == 3

    resp = _post(client, headers, "confirm", content=BAD_CSV.encode())
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "IMPORT_HAS_ERRORS"
    assert db_session.query(Product).count() == 0
    assert db_session.query(AuditLog).filter(AuditLog.entity == "product").count() == 0


def test_missing_required_column(client, db_session, base_catalogs):
    headers = login_as(client, db_session, "admin")
    csv_text = "codigo,nombre\nA1,Uno\n"
    body = _post(client, headers, "preview", content=csv_text.encode()).json()
    assert body["has_errors"] is True
    assert body["missing_columns"] == ["Proveedor", "Presentación"]


def test_xlsx_import(client, db_session, base_catalogs):
    headers = login_as(client, db_session, "admin")
    wb = Workbook()
    ws = wb.active
    ws.append(["CODIGO", "DESCRIPCION", "CATEGORIA", "Umbral stock bajo", "Existencia inicial"])
    ws.append(["ETQ0001", "Etiqueta NB-NEEM 20 L", "Etiquetas", 200, 1500])
    ws.append([None, None, None, None, None])  # blank rows are skipped
    ws.append(["TAR0001", "Tarima", "Otro", None, None])
    buf = io.BytesIO()
    wb.save(buf)

    resp = _post(
        client, headers, "confirm", kind="packaging-items", content=buf.getvalue(),
        filename="materiales.xlsx",
    )
    assert resp.status_code == 200, resp.text
    etq = db_session.query(PackagingItem).filter(PackagingItem.code == "ETQ0001").one()
    assert etq.category == "etiqueta" and etq.low_stock_threshold == 200
    tar = db_session.query(PackagingItem).filter(PackagingItem.code == "TAR0001").one()
    assert tar.low_stock_threshold == 0
    level = db_session.query(StockLevel).filter(StockLevel.packaging_item_id == etq.id).one()
    assert Decimal(level.on_hand) == 1500


def test_packaging_initial_stock_must_be_whole(client, db_session, base_catalogs):
    headers = login_as(client, db_session, "admin")
    csv_text = "codigo,descripcion,categoria,existencia_inicial\nX1,Algo,caja,2.5\n"
    body = _post(
        client, headers, "preview", kind="packaging-items", content=csv_text.encode()
    ).json()
    assert body["rows"][0]["action"] == "error"


def test_create_only_skips_existing(client, db_session, base_catalogs):
    headers = login_as(client, db_session, "admin")
    _post(client, headers, "confirm", content=VALID_CSV.encode())
    changed = VALID_CSV.replace("NB-NEEM,GRN", "NB-NEEM NUEVO,GRN")
    body = _post(client, headers, "confirm", content=changed.encode()).json()
    assert body["summary"]["skip"] == 3
    db_session.expire_all()
    p = db_session.query(Product).filter(Product.code == "GRN100C1XL20F004").one()
    assert p.name == "NB-NEEM"


def test_upsert_updates_existing_and_never_doubles_stock(client, db_session, base_catalogs):
    headers = login_as(client, db_session, "admin")
    _post(client, headers, "confirm", content=VALID_CSV.encode())

    changed = (
        VALID_CSV.replace("NB-NEEM,GRN", "NB-NEEM NUEVO,GRN")
        + "NEW0001,Nuevo,QVR,1X20,20,50\n"
    )
    preview = _post(client, headers, "preview", content=changed.encode(), mode="upsert").json()
    actions = {r["values"]["code"]: r["action"] for r in preview["rows"]}
    assert actions == {
        "GRN100C1XL20F004": "update",
        "QVR200C1XL09M01": "skip",  # no changes
        "QVR200C1XL20F003": "skip",
        "NEW0001": "create",
    }
    grn_row = next(r for r in preview["rows"] if r["values"]["code"] == "GRN100C1XL20F004")
    assert any("ignorada" in w for w in grn_row["warnings"])  # already has movements

    resp = _post(client, headers, "confirm", content=changed.encode(), mode="upsert")
    assert resp.status_code == 200
    db_session.expire_all()
    grn = db_session.query(Product).filter(Product.code == "GRN100C1XL20F004").one()
    assert grn.name == "NB-NEEM NUEVO"
    level = db_session.query(StockLevel).filter(StockLevel.product_id == grn.id).one()
    assert Decimal(level.on_hand) == Decimal("400")  # not 800
    assert db_session.query(StockMovement).count() == 3  # 2 initial + NEW0001
    update_audit = (
        db_session.query(AuditLog)
        .filter(AuditLog.entity == "product", AuditLog.action == "update")
        .one()
    )
    assert update_audit.before["name"] == "NB-NEEM"
    assert update_audit.after["name"] == "NB-NEEM NUEVO"


def test_upsert_does_not_clear_fields_left_empty(client, db_session, base_catalogs):
    headers = login_as(client, db_session, "admin")
    _post(client, headers, "confirm", content=VALID_CSV.encode())
    no_liters = VALID_CSV.replace("1X20,20,400", "1X20,,")
    _post(client, headers, "confirm", content=no_liters.encode(), mode="upsert")
    db_session.expire_all()
    grn = db_session.query(Product).filter(Product.code == "GRN100C1XL20F004").one()
    assert Decimal(grn.container_liters) == Decimal("20")


def test_unsupported_file_type(client, db_session, base_catalogs):
    headers = login_as(client, db_session, "admin")
    resp = _post(client, headers, "preview", content=b"x", filename="datos.pdf")
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "IMPORT_FILE_TYPE"


def test_cp1252_semicolon_csv(client, db_session, base_catalogs):
    headers = login_as(client, db_session, "admin")
    text = "Código;Nombre;Proveedor;Presentación\nP1;Fósforo;QVR;1X20\n"
    body = _post(client, headers, "preview", content=text.encode("cp1252")).json()
    assert body["has_errors"] is False
    assert body["rows"][0]["values"]["name"] == "Fósforo"


# External database source ------------------------------------------------------


@pytest.fixture()
def external_db(tmp_path, monkeypatch):
    """An SQLite file stands in for the (unknown) external catalog database,
    with deliberately different table/column names than ours."""
    db_file = tmp_path / "erp.db"
    conn = sqlite3.connect(db_file)
    conn.executescript(
        """
        CREATE TABLE inv_articulos (clave TEXT, descr TEXT, prov TEXT, pres TEXT,
                                    lts REAL, exist REAL, activo INTEGER);
        INSERT INTO inv_articulos VALUES
            ('GRN100C1XL20F004', 'NB-NEEM', 'GRN', '1X20', 20, 400, 1),
            ('QVR200C1XL09M01', 'BASE CALCIO', 'QVR', '1000', NULL, 1500.25, 1),
            ('OLD0001', 'Descontinuado', 'QVR', '1X20', 20, 0, 0);
        """
    )
    conn.commit()
    conn.close()

    query = tmp_path / "products.sql"
    query.write_text(
        "-- read-only mapping to canonical names\n"
        "SELECT clave AS codigo, descr AS nombre, prov AS proveedor, pres AS presentacion,\n"
        "       lts AS litros_por_envase, exist AS existencia_inicial\n"
        "FROM inv_articulos WHERE activo = 1;\n",
        encoding="utf-8",
    )
    settings = get_settings()
    monkeypatch.setattr(settings, "external_catalog_db_url", f"sqlite:///{db_file}")
    monkeypatch.setattr(settings, "external_products_query_file", str(query))
    return query


def test_external_source_listed_only_when_configured(client, db_session, base_catalogs):
    login_as(client, db_session, "admin")
    sources = client.get(f"{API}/products/sources").json()["sources"]
    assert {s["name"]: s["available"] for s in sources} == {
        "file": True, "external_db": False,
    }
    headers = login_as(client, db_session, "admin")
    resp = _post(client, headers, "preview", source="external_db")
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "EXTERNAL_SOURCE_NOT_CONFIGURED"


def test_external_db_import(client, db_session, base_catalogs, external_db):
    headers = login_as(client, db_session, "admin")
    sources = client.get(f"{API}/products/sources").json()["sources"]
    assert {s["name"]: s["available"] for s in sources}["external_db"] is True

    preview = _post(client, headers, "preview", source="external_db").json()
    assert preview["has_errors"] is False, preview
    assert preview["summary"]["create"] == 2
    assert db_session.query(Product).count() == 0

    resp = _post(client, headers, "confirm", source="external_db")
    assert resp.status_code == 200, resp.text
    codes = {p.code for p in db_session.query(Product).all()}
    assert codes == {"GRN100C1XL20F004", "QVR200C1XL09M01"}
    level = db_session.query(StockLevel).join(Product).filter(
        Product.code == "QVR200C1XL09M01"
    ).one()
    assert Decimal(level.on_hand) == Decimal("1500.25")
    entry = db_session.query(AuditLog).filter(AuditLog.entity == "import").one()
    assert entry.after["source"] == "external_db"


def test_external_db_rejects_non_select(client, db_session, base_catalogs, external_db):
    headers = login_as(client, db_session, "admin")
    external_db.write_text("DELETE FROM inv_articulos", encoding="utf-8")
    resp = _post(client, headers, "preview", source="external_db")
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "EXTERNAL_SOURCE_INVALID_QUERY"


def test_external_db_query_error(client, db_session, base_catalogs, external_db):
    headers = login_as(client, db_session, "admin")
    external_db.write_text("SELECT * FROM tabla_que_no_existe", encoding="utf-8")
    resp = _post(client, headers, "preview", source="external_db")
    assert resp.status_code == 502
    assert resp.json()["error"]["code"] == "EXTERNAL_SOURCE_ERROR"


def test_import_requires_catalogs_manage(client, db_session, base_catalogs):
    headers = login_as(client, db_session, "supervisor")
    resp = _post(client, headers, "preview", content=VALID_CSV.encode())
    assert resp.status_code == 403
