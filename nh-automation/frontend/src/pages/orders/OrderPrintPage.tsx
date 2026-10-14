import { Alert, Button, Center, Group, Loader } from "@mantine/core";
import { IconArrowLeft, IconPrinter } from "@tabler/icons-react";
import { useQuery } from "@tanstack/react-query";
import JsBarcode from "jsbarcode";
import { useEffect, useRef } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { ordersApi } from "../../api/orders";
import { strings } from "../../i18n/strings";
import { formatDateTime, formatLiters } from "../../utils/datetime";
import { errorMessage } from "../../utils/notify";
import { formatExpiry, formatPlainDate } from "../../utils/orders";
import { differenceKind } from "../../utils/production";
import { formatUnits } from "../../utils/quantity";

const t = strings.orders;
const f = t.form;
const p = t.print;
const pr = strings.production;

/** Letter-size print layout; screen-only toolbar is hidden when printing. */
const PRINT_CSS = `
@page { size: letter; margin: 12mm; }
.op-print { font-family: Arial, Helvetica, sans-serif; font-size: 11px; color: #000;
  background: #fff; max-width: 8.5in; margin: 0 auto; padding: 16px; }
.op-print h1 { font-size: 18px; margin: 0; }
.op-print h2 { font-size: 12px; margin: 10px 0 4px; padding: 2px 6px; background: #e5e5e5;
  border: 1px solid #000; text-transform: uppercase; }
.op-print table { width: 100%; border-collapse: collapse; }
.op-print th, .op-print td { border: 1px solid #000; padding: 3px 5px; text-align: left;
  vertical-align: top; }
.op-print th { background: #f2f2f2; font-weight: 700; }
.op-print td.num, .op-print th.num { text-align: right; }
.op-print .head { display: flex; justify-content: space-between; align-items: flex-start;
  border: 2px solid #000; padding: 8px; }
.op-print .type { display: inline-block; border: 2px solid #000; padding: 2px 10px;
  font-weight: 700; font-size: 14px; letter-spacing: 1px; margin-top: 4px; }
.op-print .opnum { font-size: 20px; font-weight: 700; text-align: right; }
.op-print .grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 0; }
.op-print .cell { border: 1px solid #000; padding: 3px 5px; margin: -1px 0 0 -1px; }
.op-print .lbl { font-size: 9px; color: #333; text-transform: uppercase; }
.op-print .val { font-weight: 600; min-height: 13px; }
.op-print .barcodes { display: flex; justify-content: space-around; margin-top: 10px; }
.op-print .barcodes svg { max-width: 100%; }
.op-print .avoid-break { break-inside: avoid; }
@media print {
  .no-print { display: none !important; }
  body { background: #fff !important; }
  .op-print { padding: 0; max-width: none; }
}
`;

function Barcode({ value }: { value: string }) {
  const ref = useRef<SVGSVGElement>(null);
  useEffect(() => {
    if (ref.current && value) {
      JsBarcode(ref.current, value, {
        format: "CODE128",
        height: 45,
        width: 1.6,
        fontSize: 12,
        margin: 4,
      });
    }
  }, [value]);
  return <svg ref={ref} />;
}

function Cell({ label, value, span = 1 }: { label: string; value: string; span?: number }) {
  return (
    <div className="cell" style={{ gridColumn: `span ${span}` }}>
      <div className="lbl">{label}</div>
      <div className="val">{value}</div>
    </div>
  );
}

/** FR-ORD-6: `/ordenes/:id/imprimir`. TODO(OPEN-12): label/barcode printing details. */
export function OrderPrintPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { data, error } = useQuery({
    queryKey: ["orders", Number(id), "print-data"],
    queryFn: () => ordersApi.printData(Number(id)),
  });

  if (error) {
    return (
      <Center h="50vh">
        <Alert color="red">{errorMessage(error)}</Alert>
      </Center>
    );
  }
  if (!data) {
    return (
      <Center h="50vh">
        <Loader />
      </Center>
    );
  }
  const { order, comments } = data;
  const isRework = order.order_type === "retrabajo";
  const expiry = order.expiry_date ? formatExpiry(order.expiry_date) : f.caducidadPendiente;
  const signature = (s: { name: string; at: string } | null) =>
    s ? `${s.name} · ${formatDateTime(s.at)}` : "";
  const assignments = order.assignments.filter((a) => a.status !== "cancelled");
  const diff = order.difference;
  const diffText = (() => {
    if (!diff) return "";
    const { kind, liters } = differenceKind(diff.difference);
    if (kind === "none") return pr.sinDiferencia;
    const label = `${kind === "faltante" ? pr.faltante : pr.excedente} ${formatLiters(liters)}`;
    return diff.within_range ? label : `${label} (${pr.fueraDeRango})`;
  })();

  return (
    <>
      <style>{PRINT_CSS}</style>
      <Group className="no-print" justify="center" p="md" gap="sm">
        <Button
          variant="default"
          leftSection={<IconArrowLeft size={16} />}
          onClick={() => navigate(`/ordenes/${order.id}`)}
        >
          {t.detalle.volver}
        </Button>
        <Button leftSection={<IconPrinter size={16} />} onClick={() => window.print()}>
          {p.imprimir}
        </Button>
      </Group>

      <div className="op-print">
        <div className="head">
          <div>
            <h1>{order.razon_social_name}</h1>
            <div>{order.site_name}</div>
            <div style={{ fontSize: 14, fontWeight: 700, marginTop: 6 }}>
              {isRework ? p.tituloRetrabajo : p.titulo}
            </div>
            <div className="type">{t.tipos[order.order_type]}</div>
          </div>
          <div>
            <div className="lbl" style={{ textAlign: "right" }}>
              {f.numero}
            </div>
            <div className="opnum">{order.operation_number}</div>
            <div style={{ textAlign: "right" }}>
              {t.estados[order.status]} · {formatPlainDate(order.order_date)}
            </div>
          </div>
        </div>

        <h2>{f.secciones.general}</h2>
        <div className="grid">
          <Cell label={f.cliente} value={order.client_name ?? f.sinCliente} span={2} />
          <Cell label={f.fecha} value={formatPlainDate(order.order_date)} />
          <Cell
            label={f.razonSocial}
            value={`${order.razon_social_code} — ${order.razon_social_name}`}
            span={2}
          />
          <Cell label={f.lugar} value={order.site_name} />
          {isRework && (
            <>
              <Cell
                label={f.tipoRetrabajo}
                value={order.rework_kind ? t.reworkKinds[order.rework_kind] : ""}
                span={2}
              />
              <Cell label={f.ordenRelacionada} value={order.related_operation_number ?? "—"} />
            </>
          )}
        </div>

        <h2>{f.secciones.base}</h2>
        <table>
          <thead>
            <tr>
              <th>{p.codigo}</th>
              <th>{p.nombre}</th>
              <th>{p.proveedor}</th>
              <th>{p.presentacion}</th>
              <th className="num">{p.cantidad}</th>
            </tr>
          </thead>
          <tbody>
            {order.base_products.map((b) => (
              <tr key={b.position}>
                <td>{b.code}</td>
                <td>{b.name}</td>
                <td>{b.provider}</td>
                <td>{b.presentation}</td>
                <td className="num">{formatLiters(b.liters)}</td>
              </tr>
            ))}
            {order.base_products.length > 1 && (
              <tr>
                <th colSpan={4}>{f.totalBase}</th>
                <th className="num">{formatLiters(order.base_liters_total)}</th>
              </tr>
            )}
          </tbody>
        </table>

        <h2>{f.secciones.terminado}</h2>
        <table>
          <thead>
            <tr>
              <th>{p.codigo}</th>
              <th>{p.nombre}</th>
              <th>{p.proveedor}</th>
              <th>{p.presentacion}</th>
              <th className="num">{p.cantidad}</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>{order.finished_code}</td>
              <td>{order.finished_name}</td>
              <td>{order.finished_provider}</td>
              <td>{order.finished_presentation}</td>
              <td className="num">{formatLiters(order.finished_liters)}</td>
            </tr>
          </tbody>
        </table>

        {assignments.length > 0 && (
          <div className="avoid-break">
            <h2>{p.maquinas}</h2>
            <table>
              <thead>
                <tr>
                  <th>{p.maquina}</th>
                  <th>{pr.estado}</th>
                  <th className="num">{p.planeado}</th>
                  <th className="num">{p.real}</th>
                </tr>
              </thead>
              <tbody>
                {assignments.map((a) => (
                  <tr key={a.id}>
                    <td>{a.machine_code}</td>
                    <td>{pr.asignacion[a.status]}</td>
                    <td className="num">{formatLiters(a.planned_liters)}</td>
                    <td className="num">
                      {a.actual_liters === null ? "" : formatLiters(a.actual_liters)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {diff && (
              <div className="grid" style={{ marginTop: 4 }}>
                <Cell label={pr.ordenado} value={formatLiters(diff.ordered_liters)} />
                <Cell label={pr.real} value={formatLiters(diff.actual_liters)} />
                <Cell label={pr.diferencia} value={diffText} />
              </div>
            )}
          </div>
        )}

        <div className="avoid-break">
          <h2>{f.secciones.empaque}</h2>
          <table>
            <thead>
              <tr>
                <th>{p.codigo}</th>
                <th>{f.material}</th>
                <th className="num">{f.cantidadPlaneada}</th>
                <th className="num">{p.usado}</th>
              </tr>
            </thead>
            <tbody>
              {order.packaging.length === 0 && (
                <tr>
                  <td colSpan={4}>{t.detalle.sinMaterial}</td>
                </tr>
              )}
              {order.packaging.map((m) => (
                <tr key={m.packaging_item_id}>
                  <td>{m.code}</td>
                  <td>{m.description}</td>
                  <td className="num">{formatUnits(m.planned_qty)}</td>
                  <td className="num">{m.actual_qty === null ? "" : formatUnits(m.actual_qty)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="grid" style={{ marginTop: 4 }}>
            <Cell
              label={`${f.totalEtiquetas} — ${t.detalle.planeado}`}
              value={order.labels_planned === null ? "" : formatUnits(order.labels_planned)}
            />
            <Cell
              label={`${f.totalEtiquetas} — ${p.usado}`}
              value={order.labels_actual === null ? "" : formatUnits(order.labels_actual)}
            />
            <Cell label={f.codigoBarras} value={t.barcodeModes[order.barcode_mode]} />
          </div>
        </div>

        <div className="avoid-break">
          <h2>{t.detalle.tabs.checklist}</h2>
          <table>
            <tbody>
              {order.checklist.map((c) => (
                <tr key={c.item}>
                  <td style={{ width: 24, textAlign: "center" }}>{c.checked ? "☑" : "☐"}</td>
                  <td>{t.checklist[c.item]}</td>
                  <td style={{ width: "40%" }}>
                    {c.checked_by_name
                      ? `${c.checked_by_name} · ${formatDateTime(c.checked_at)}`
                      : ""}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="avoid-break">
          <h2>{p.lotes}</h2>
          <div className="grid">
            <Cell label={t.detalle.loteAnterior} value={order.previous_lot ?? ""} />
            <Cell label={t.detalle.lotePosterior} value={order.new_lot ?? ""} />
            <Cell label={f.caducidad} value={expiry} />
          </div>
        </div>

        <div className="avoid-break">
          <h2>{p.comentarios}</h2>
          <table>
            <tbody>
              {comments.length === 0 && (
                <tr>
                  <td>{t.detalle.sinComentarios}</td>
                </tr>
              )}
              {comments.map((c) => (
                <tr key={c.id}>
                  <td style={{ width: "30%" }}>
                    {c.user_name}
                    <br />
                    {formatDateTime(c.created_at)}
                  </td>
                  <td style={{ whiteSpace: "pre-wrap" }}>{c.text}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="avoid-break">
          <h2>{p.firmas}</h2>
          <div className="grid">
            <Cell label={p.elaboro} value={signature(data.created)} />
            <Cell label={p.asigno} value={signature(data.assigned)} />
            <Cell label={p.cerro} value={signature(data.closed)} />
            {order.close_note && <Cell label={p.notaCierre} value={order.close_note} span={3} />}
          </div>
          <div className="barcodes">
            <Barcode value={data.barcodes.operation_number} />
            <Barcode value={data.barcodes.finished_code} />
          </div>
        </div>
      </div>
    </>
  );
}
