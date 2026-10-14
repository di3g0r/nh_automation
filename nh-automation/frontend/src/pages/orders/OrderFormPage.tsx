import {
  ActionIcon,
  Alert,
  Anchor,
  Button,
  Center,
  Checkbox,
  Grid,
  Group,
  Loader,
  Paper,
  Radio,
  Select,
  Stack,
  Text,
  TextInput,
  Textarea,
  Title,
  Tooltip,
} from "@mantine/core";
import { useDebouncedValue } from "@mantine/hooks";
import { notifications } from "@mantine/notifications";
import { IconAlertTriangle, IconPlus, IconTrash } from "@tabler/icons-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { clientsApi, packagingApi, productsApi, sitesApi } from "../../api/catalogs";
import { ApiError } from "../../api/client";
import { inventoryApi } from "../../api/inventory";
import { ordersApi } from "../../api/orders";
import type {
  BarcodeMode,
  Order,
  OrderPayload,
  PackagingShortageWarning,
  Product,
  ReworkKind,
  ShortageItem,
} from "../../api/types";
import { OrderTypeBadge } from "../../components/orders/OrderBadges";
import { ProductSelect } from "../../components/orders/ProductSelect";
import { strings } from "../../i18n/strings";
import { formatLiters } from "../../utils/datetime";
import { notifyError } from "../../utils/notify";
import { formatExpiry, localToday, razonSocialOptions, sumLiters } from "../../utils/orders";
import { formatUnits } from "../../utils/quantity";

const t = strings.orders;
const f = t.form;

interface BaseRow {
  key: number;
  product: Product | null;
  liters: string;
}

interface PackagingRow {
  key: number;
  itemId: string | null;
  qty: string;
}

interface RelatedRef {
  id: number;
  operation_number: string;
  expiry_date: string | null;
}

let rowKey = 0;
const nextKey = () => ++rowKey;

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <Paper withBorder p="md">
      <Title order={4} mb="sm">
        {title}
      </Title>
      {children}
    </Paper>
  );
}

/** Entry point: `/ordenes/nueva` or `/ordenes/:id/editar`. */
export function OrderFormPage() {
  const { id } = useParams();
  const orderId = id ? Number(id) : null;
  const { data: order, isLoading } = useQuery({
    queryKey: ["orders", orderId],
    queryFn: () => ordersApi.get(orderId as number),
    enabled: orderId !== null,
  });
  // Products referenced by the order, loaded once to fill the pickers.
  const productIds = order
    ? [...order.base_products.map((b) => b.product_id), order.finished_product_id]
    : [];
  const { data: products, isLoading: loadingProducts } = useQuery({
    queryKey: ["orders", orderId, "form-products", productIds],
    queryFn: () => Promise.all(productIds.map((pid) => productsApi.get(pid))),
    enabled: !!order,
  });

  if (orderId === null) return <OrderForm />;
  if (isLoading || loadingProducts || !order || !products) {
    return (
      <Center h="50vh">
        <Loader />
      </Center>
    );
  }
  if (!order.can_edit) {
    return (
      <Stack>
        <Alert color="orange">{t.detalle.noEditable}</Alert>
        <Anchor component={Link} to={`/ordenes/${order.id}`}>
          {t.detalle.volver}
        </Anchor>
      </Stack>
    );
  }
  return <OrderForm order={order} products={products} />;
}

function OrderForm({ order, products }: { order?: Order; products?: Product[] }) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const isEdit = !!order;
  const productById = new Map((products ?? []).map((p) => [p.id, p]));

  const [isRework, setIsRework] = useState(order?.order_type === "retrabajo");
  const [reworkKind, setReworkKind] = useState<ReworkKind | null>(order?.rework_kind ?? null);
  const [related, setRelated] = useState<RelatedRef | null>(
    order?.related_order_id
      ? {
          id: order.related_order_id,
          operation_number: order.related_operation_number ?? "",
          expiry_date: order.expiry_date,
        }
      : null,
  );
  const [clientId, setClientId] = useState<string | null>(
    order?.client_id ? String(order.client_id) : null,
  );
  const [siteId, setSiteId] = useState<string | null>(order ? String(order.site_id) : null);
  const [orderDate, setOrderDate] = useState(order?.order_date ?? localToday());
  const [baseRows, setBaseRows] = useState<BaseRow[]>(
    order
      ? order.base_products.map((b) => ({
          key: nextKey(),
          product: productById.get(b.product_id) ?? null,
          liters: b.liters,
        }))
      : [{ key: nextKey(), product: null, liters: "" }],
  );
  const [finished, setFinished] = useState<Product | null>(
    order ? (productById.get(order.finished_product_id) ?? null) : null,
  );
  // Finished liters follow the base sum until the user edits them.
  const [finishedLiters, setFinishedLiters] = useState(order?.finished_liters ?? "");
  const [finishedTouched, setFinishedTouched] = useState(isEdit);
  const [rsId, setRsId] = useState<string | null>(null);
  const [comment, setComment] = useState("");
  const [packagingRows, setPackagingRows] = useState<PackagingRow[]>(
    order?.packaging.map((p) => ({
      key: nextKey(),
      itemId: String(p.packaging_item_id),
      qty: String(p.planned_qty),
    })) ?? [],
  );
  const [labels, setLabels] = useState(order?.labels_planned?.toString() ?? "");
  const [barcodeMode, setBarcodeMode] = useState<BarcodeMode>(
    order?.barcode_mode ?? "per_container",
  );
  const [previousLot, setPreviousLot] = useState(order?.previous_lot ?? "");
  const [shortages, setShortages] = useState<ShortageItem[]>([]);

  const ownStock = isRework && reworkKind === "own_stock";
  const fromPrevious = isRework && reworkKind === "previous_order";

  // Options ------------------------------------------------------------------
  const { data: sites } = useQuery({
    queryKey: ["sites", "active-for-select"],
    queryFn: () => sitesApi.list({ active: true, page_size: 500 }),
  });
  useEffect(() => {
    if (siteId === null && sites) {
      const def = sites.items.find((s) => s.is_default);
      if (def) setSiteId(String(def.id));
    }
  }, [sites, siteId]);
  const { data: clients } = useQuery({
    queryKey: ["clients", "active-for-select"],
    queryFn: () => clientsApi.list({ active: true, page_size: 500 }),
  });
  const { data: packagingItems } = useQuery({
    queryKey: ["packaging-items", "active-for-select"],
    queryFn: () => packagingApi.list({ active: true, page_size: 500 }),
  });
  const clientOptions = useMemo(() => {
    const opts = clients?.items.map((c) => ({ value: String(c.id), label: c.name })) ?? [];
    // Keep an inactive client already on the order visible.
    if (order?.client_id && !opts.some((o) => o.value === String(order.client_id))) {
      opts.unshift({ value: String(order.client_id), label: order.client_name ?? "" });
    }
    return opts;
  }, [clients, order]);
  const packagingOptions = useMemo(() => {
    const opts =
      packagingItems?.items.map((p) => ({
        value: String(p.id),
        label: `${p.code} — ${p.description}`,
      })) ?? [];
    for (const p of order?.packaging ?? []) {
      if (!opts.some((o) => o.value === String(p.packaging_item_id))) {
        opts.push({ value: String(p.packaging_item_id), label: `${p.code} — ${p.description}` });
      }
    }
    return opts;
  }, [packagingItems, order]);

  // Derived values -----------------------------------------------------------
  const baseSum = sumLiters(baseRows.map((r) => r.liters));
  const shownFinishedLiters = finishedTouched ? finishedLiters : baseSum;
  const rsOptions = razonSocialOptions(baseRows.map((r) => r.product));
  useEffect(() => {
    if (rsId && !rsOptions.some((o) => String(o.id) === rsId)) setRsId(null);
  }, [rsOptions, rsId]);

  // Related order (Retrabajo de orden anterior) prefills client, finished product, expiry.
  const selectRelated = async (orderIdValue: string | null) => {
    if (!orderIdValue) {
      setRelated(null);
      return;
    }
    try {
      const rel = await ordersApi.get(Number(orderIdValue));
      setRelated({
        id: rel.id,
        operation_number: rel.operation_number,
        expiry_date: rel.expiry_date,
      });
      if (rel.client_id) setClientId(String(rel.client_id));
      setFinished(await productsApi.get(rel.finished_product_id));
    } catch (err) {
      notifyError(err);
    }
  };

  // Save ---------------------------------------------------------------------
  const buildPayload = (): OrderPayload => {
    const payload: OrderPayload = {
      rework_kind: isRework ? reworkKind : null,
      related_order_id: fromPrevious ? (related?.id ?? null) : null,
      client_id: ownStock ? null : clientId ? Number(clientId) : null,
      site_id: siteId ? Number(siteId) : null,
      order_date: orderDate || null,
      base_products: baseRows
        .filter((r) => r.product)
        .map((r) => ({ product_id: (r.product as Product).id, liters: r.liters })),
      finished_product_id: finished?.id,
      finished_liters: shownFinishedLiters,
      comment: comment.trim() || null,
      packaging: packagingRows
        .filter((r) => r.itemId)
        .map((r) => ({ packaging_item_id: Number(r.itemId), planned_qty: Number(r.qty) })),
      labels_planned: labels === "" ? null : Number(labels),
      barcode_mode: barcodeMode,
      previous_lot: previousLot.trim() || null,
    };
    if (!isEdit) {
      payload.order_type = isRework ? "retrabajo" : "trabajo";
      payload.razon_social_id = rsOptions.length > 1 && rsId ? Number(rsId) : null;
    }
    return payload;
  };

  const mutation = useMutation({
    mutationFn: (payload: OrderPayload) =>
      isEdit ? ordersApi.update(order.id, payload) : ordersApi.create(payload),
    onSuccess: (saved) => {
      queryClient.invalidateQueries({ queryKey: ["orders"] });
      queryClient.invalidateQueries({ queryKey: ["inventory"] });
      notifications.show({
        color: "green",
        message: isEdit ? f.actualizada : `${f.creada}: ${saved.operation_number}`,
      });
      if (saved.warnings.length) {
        notifications.show({
          color: "orange",
          autoClose: 10000,
          title: f.avisoEmpaque,
          message: saved.warnings.map(warningText).join(" · "),
        });
      }
      navigate(`/ordenes/${saved.id}`);
    },
    onError: (err) => {
      if (err instanceof ApiError && err.code === "INSUFFICIENT_STOCK") {
        setShortages((err.details.items as ShortageItem[]) ?? []);
        window.scrollTo({ top: 0, behavior: "smooth" });
        return;
      }
      setShortages([]);
      notifyError(err);
    },
  });

  const missing =
    !baseRows.some((r) => r.product && Number(r.liters) > 0) ||
    !finished ||
    (!ownStock && !clientId && !fromPrevious) ||
    (isRework && !reworkKind) ||
    (fromPrevious && !related) ||
    (!isEdit && rsOptions.length > 1 && !rsId);

  const submit = () => {
    setShortages([]);
    mutation.mutate(buildPayload());
  };

  const usedProductIds = baseRows.map((r) => r.product?.id).filter((x): x is number => !!x);
  const usedPackagingIds = packagingRows.map((r) => r.itemId).filter(Boolean);

  return (
    <Stack maw={1100}>
      <Group justify="space-between">
        <Group>
          <Title order={2}>{isEdit ? t.editarTitulo : t.nueva}</Title>
          {isEdit && <OrderTypeBadge type={order.order_type} size="lg" />}
          {isEdit && (
            <Text fw={700} size="lg">
              {order.operation_number}
            </Text>
          )}
        </Group>
      </Group>

      {shortages.length > 0 && (
        <Alert color="red" icon={<IconAlertTriangle />} title={f.stockInsuficiente}>
          <Stack gap={4}>
            {shortages.map((s) => (
              <Text key={s.product_id} size="sm">
                <b>{s.name}</b> ({s.code}): {strings.inventory.columnas.existencia.toLowerCase()}{" "}
                {formatLiters(s.on_hand)}, {strings.inventory.columnas.reservado.toLowerCase()}{" "}
                {formatLiters(s.reserved)}, {strings.inventory.columnas.disponible.toLowerCase()}{" "}
                {formatLiters(s.available)} — {f.litros.toLowerCase()} {formatLiters(s.required)}
                {s.orders.length > 0 &&
                  ` · ${strings.inventory.reservas.orden}: ${s.orders
                    .map((o) => `${o.operation_number} (${formatLiters(o.quantity)})`)
                    .join(", ")}`}
              </Text>
            ))}
          </Stack>
        </Alert>
      )}

      <Section title={f.secciones.general}>
        <Stack>
          {isEdit ? (
            <Text size="sm" c="dimmed">
              {f.tipoFijo}
            </Text>
          ) : (
            <Checkbox
              size="md"
              label={f.retrabajo}
              description={f.retrabajoHint}
              checked={isRework}
              onChange={(e) => {
                setIsRework(e.currentTarget.checked);
                if (!e.currentTarget.checked) {
                  setReworkKind(null);
                  setRelated(null);
                }
              }}
            />
          )}
          {isRework && (
            <Radio.Group
              label={f.tipoRetrabajo}
              required
              value={reworkKind}
              onChange={(v) => setReworkKind(v as ReworkKind)}
            >
              <Group mt={4}>
                <Radio value="previous_order" label={t.reworkKinds.previous_order} />
                <Radio value="own_stock" label={t.reworkKinds.own_stock} />
              </Group>
            </Radio.Group>
          )}
          {fromPrevious && (
            <RelatedOrderSelect value={related} onChange={selectRelated} excludeId={order?.id} />
          )}
          <Grid>
            <Grid.Col span={{ base: 12, sm: 6 }}>
              {ownStock ? (
                <TextInput label={f.cliente} value={f.sinCliente} disabled />
              ) : (
                <Select
                  label={f.cliente}
                  data={clientOptions}
                  value={clientId}
                  onChange={setClientId}
                  searchable
                  required
                  nothingFoundMessage={strings.common.sinDatos}
                />
              )}
            </Grid.Col>
            <Grid.Col span={{ base: 12, sm: 3 }}>
              <Select
                label={f.lugar}
                data={sites?.items.map((s) => ({ value: String(s.id), label: s.name })) ?? []}
                value={siteId}
                onChange={setSiteId}
                allowDeselect={false}
              />
            </Grid.Col>
            <Grid.Col span={{ base: 12, sm: 3 }}>
              <TextInput
                type="date"
                label={f.fecha}
                value={orderDate}
                onChange={(e) => setOrderDate(e.currentTarget.value)}
              />
            </Grid.Col>
          </Grid>
          <Grid>
            <Grid.Col span={{ base: 12, sm: 6 }}>
              <RazonSocialField
                order={order}
                options={rsOptions}
                value={rsId}
                onChange={setRsId}
              />
            </Grid.Col>
            <Grid.Col span={{ base: 12, sm: 6 }}>
              <TextInput
                label={f.numero}
                value={order?.operation_number ?? f.numeroAlGuardar}
                readOnly
                variant="filled"
              />
            </Grid.Col>
          </Grid>
        </Stack>
      </Section>

      <Section title={f.secciones.base}>
        <Stack>
          {baseRows.map((row, idx) => (
            <BaseProductRowEditor
              key={row.key}
              row={row}
              siteId={siteId ? Number(siteId) : null}
              excludeOrderId={order?.id ?? null}
              usedIds={usedProductIds}
              canRemove={baseRows.length > 1}
              onChange={(next) =>
                setBaseRows((rows) => rows.map((r, i) => (i === idx ? next : r)))
              }
              onRemove={() => setBaseRows((rows) => rows.filter((_, i) => i !== idx))}
            />
          ))}
          <Group justify="space-between">
            <Button
              variant="light"
              leftSection={<IconPlus size={16} />}
              onClick={() =>
                setBaseRows((rows) => [...rows, { key: nextKey(), product: null, liters: "" }])
              }
            >
              {f.agregarProducto}
            </Button>
            <Text fw={600}>
              {f.totalBase}: {formatLiters(baseSum)}
            </Text>
          </Group>
        </Stack>
      </Section>

      <Section title={f.secciones.terminado}>
        <Grid>
          <Grid.Col span={{ base: 12, sm: 8 }}>
            <ProductSelect
              label={f.producto}
              value={finished}
              onChange={setFinished}
              required
              clearable={false}
            />
          </Grid.Col>
          <Grid.Col span={{ base: 12, sm: 4 }}>
            <TextInput
              type="number"
              min={0}
              step="0.01"
              label={f.litrosTerminado}
              description={f.litrosTerminadoHint}
              value={shownFinishedLiters}
              onChange={(e) => {
                setFinishedTouched(true);
                setFinishedLiters(e.currentTarget.value);
              }}
              required
            />
          </Grid.Col>
        </Grid>
      </Section>

      <Section title={f.secciones.empaque}>
        <Stack>
          {packagingRows.map((row, idx) => (
            <Group key={row.key} align="end" wrap="nowrap">
              <Select
                label={idx === 0 ? f.material : undefined}
                data={packagingOptions.map((o) => ({
                  ...o,
                  disabled: usedPackagingIds.includes(o.value) && o.value !== row.itemId,
                }))}
                value={row.itemId}
                onChange={(v) =>
                  setPackagingRows((rows) =>
                    rows.map((r, i) => (i === idx ? { ...r, itemId: v } : r)),
                  )
                }
                searchable
                style={{ flex: 1 }}
              />
              <PackagingAvailability
                itemId={row.itemId ? Number(row.itemId) : null}
                siteId={siteId ? Number(siteId) : null}
                excludeOrderId={order?.id ?? null}
                qty={row.qty}
              />
              <TextInput
                type="number"
                min={1}
                step={1}
                label={idx === 0 ? f.cantidadPlaneada : undefined}
                value={row.qty}
                onChange={(e) => {
                  const v = e.currentTarget.value;
                  setPackagingRows((rows) => rows.map((r, i) => (i === idx ? { ...r, qty: v } : r)));
                }}
                w={150}
              />
              <Tooltip label={f.quitar}>
                <ActionIcon
                  variant="subtle"
                  color="red"
                  aria-label={f.quitar}
                  onClick={() => setPackagingRows((rows) => rows.filter((_, i) => i !== idx))}
                  mb={4}
                >
                  <IconTrash size={16} />
                </ActionIcon>
              </Tooltip>
            </Group>
          ))}
          <Group>
            <Button
              variant="light"
              leftSection={<IconPlus size={16} />}
              onClick={() =>
                setPackagingRows((rows) => [...rows, { key: nextKey(), itemId: null, qty: "" }])
              }
            >
              {f.agregarMaterial}
            </Button>
          </Group>
          <Grid>
            <Grid.Col span={{ base: 12, sm: 4 }}>
              <TextInput
                type="number"
                min={0}
                step={1}
                label={f.totalEtiquetas}
                value={labels}
                onChange={(e) => setLabels(e.currentTarget.value)}
              />
            </Grid.Col>
            <Grid.Col span={{ base: 12, sm: 8 }}>
              <Radio.Group
                label={f.codigoBarras}
                value={barcodeMode}
                onChange={(v) => setBarcodeMode(v as BarcodeMode)}
              >
                <Group mt={8}>
                  <Radio value="per_container" label={t.barcodeModes.per_container} />
                  <Radio value="per_box" label={t.barcodeModes.per_box} />
                </Group>
              </Radio.Group>
            </Grid.Col>
          </Grid>
        </Stack>
      </Section>

      <Section title={f.secciones.comentario}>
        <Textarea
          label={isEdit ? f.comentarioEditar : f.comentario}
          value={comment}
          onChange={(e) => setComment(e.currentTarget.value)}
          autosize
          minRows={2}
          maxLength={2000}
        />
      </Section>

      <Section title={f.secciones.trazabilidad}>
        <Grid>
          <Grid.Col span={{ base: 12, sm: 6 }}>
            {/* TODO(OPEN-4): lot format undecided; free text. */}
            <TextInput
              label={f.loteAnterior}
              value={previousLot}
              onChange={(e) => setPreviousLot(e.currentTarget.value)}
              maxLength={100}
            />
          </Grid.Col>
          <Grid.Col span={{ base: 12, sm: 6 }}>
            <TextInput
              label={f.caducidad}
              readOnly
              variant="filled"
              value={
                fromPrevious && related
                  ? formatExpiry(related.expiry_date)
                  : order?.expiry_date
                    ? formatExpiry(order.expiry_date)
                    : f.caducidadPendiente
              }
              description={fromPrevious ? f.caducidadCopiada : undefined}
            />
          </Grid.Col>
        </Grid>
      </Section>

      <Group justify="flex-end">
        <Button
          variant="default"
          onClick={() => navigate(isEdit ? `/ordenes/${order.id}` : "/ordenes")}
        >
          {f.cancelar}
        </Button>
        <Tooltip label={f.faltan} disabled={!missing}>
          <Button onClick={submit} loading={mutation.isPending} disabled={missing}>
            {isEdit ? f.guardarCambios : f.guardar}
          </Button>
        </Tooltip>
      </Group>
    </Stack>
  );
}

function warningText(w: PackagingShortageWarning): string {
  return `${w.code}: ${formatUnits(w.planned)} / ${strings.alerts.disponible} ${formatUnits(
    w.available,
  )}`;
}

function RazonSocialField({
  order,
  options,
  value,
  onChange,
}: {
  order?: Order;
  options: { id: number; code: string; name: string }[];
  value: string | null;
  onChange: (v: string | null) => void;
}) {
  if (order) {
    return (
      <TextInput
        label={f.razonSocial}
        value={`${order.razon_social_code} — ${order.razon_social_name}`}
        description={f.razonSocialFija}
        readOnly
        variant="filled"
      />
    );
  }
  if (options.length > 1) {
    return (
      <Select
        label={f.razonSocial}
        description={f.razonSocialElegir}
        data={options.map((o) => ({ value: String(o.id), label: `${o.code} — ${o.name}` }))}
        value={value}
        onChange={onChange}
        required
      />
    );
  }
  return (
    <TextInput
      label={f.razonSocial}
      value={options.length === 1 ? `${options[0].code} — ${options[0].name}` : "—"}
      description={f.razonSocialAuto}
      readOnly
      variant="filled"
    />
  );
}

function BaseProductRowEditor({
  row,
  siteId,
  excludeOrderId,
  usedIds,
  canRemove,
  onChange,
  onRemove,
}: {
  row: BaseRow;
  siteId: number | null;
  excludeOrderId: number | null;
  usedIds: number[];
  canRemove: boolean;
  onChange: (r: BaseRow) => void;
  onRemove: () => void;
}) {
  const productId = row.product?.id ?? null;
  const { data: avail } = useQuery({
    queryKey: ["inventory", "availability", "product", productId, siteId, excludeOrderId],
    queryFn: () =>
      inventoryApi.availability("product", productId as number, siteId as number, excludeOrderId),
    enabled: productId !== null && siteId !== null,
  });
  const short = avail && row.liters !== "" && Number(avail.available) < Number(row.liters);
  const noRs = row.product && row.product.razon_social_id === null;

  return (
    <Group align="start" wrap="nowrap">
      <Stack gap={2} style={{ flex: 1 }}>
        <ProductSelect
          value={row.product}
          onChange={(p) => onChange({ ...row, product: p })}
          disabledIds={usedIds}
          error={noRs ? f.sinRazonSocial : null}
        />
        {row.product && (
          <Group gap="md">
            {avail && (
              <Text size="xs" c={short ? "red" : "dimmed"} fw={short ? 700 : undefined}>
                {f.disponible}: {formatLiters(avail.available)}
              </Text>
            )}
            {row.product.razon_social_code && (
              <Text size="xs" c="dimmed">
                {f.razonSocial}: {row.product.razon_social_code}
              </Text>
            )}
          </Group>
        )}
      </Stack>
      <TextInput
        type="number"
        min={0}
        step="0.01"
        placeholder={f.litros}
        value={row.liters}
        onChange={(e) => onChange({ ...row, liters: e.currentTarget.value })}
        error={short ? true : undefined}
        w={150}
        rightSection={<Text size="xs">L</Text>}
      />
      <Tooltip label={f.quitar}>
        <ActionIcon
          variant="subtle"
          color="red"
          aria-label={f.quitar}
          disabled={!canRemove}
          onClick={onRemove}
          mt={6}
        >
          <IconTrash size={16} />
        </ActionIcon>
      </Tooltip>
    </Group>
  );
}

function PackagingAvailability({
  itemId,
  siteId,
  excludeOrderId,
  qty,
}: {
  itemId: number | null;
  siteId: number | null;
  excludeOrderId: number | null;
  qty: string;
}) {
  const { data } = useQuery({
    queryKey: ["inventory", "availability", "packaging", itemId, siteId, excludeOrderId],
    queryFn: () =>
      inventoryApi.availability("packaging", itemId as number, siteId as number, excludeOrderId),
    enabled: itemId !== null && siteId !== null,
  });
  if (!data) return <div style={{ width: 150 }} />;
  const short = qty !== "" && Number(data.available) < Number(qty);
  return (
    <Text size="xs" c={short ? "orange" : "dimmed"} w={150} mb={10}>
      {f.disponible}: {formatUnits(data.available)}
    </Text>
  );
}

function RelatedOrderSelect({
  value,
  onChange,
  excludeId,
}: {
  value: RelatedRef | null;
  onChange: (id: string | null) => void;
  excludeId?: number;
}) {
  const [search, setSearch] = useState("");
  const [debounced] = useDebouncedValue(search, 250);
  // Mantine puts the selected label in the search box; don't query with it.
  const selectedLabel = useRef<string | null>(null);
  const term = debounced === selectedLabel.current ? "" : debounced;
  const { data } = useQuery({
    queryKey: ["orders", "related-select", term],
    queryFn: () =>
      ordersApi.list({ status: "completed,closed", search: term || undefined, page_size: 50 }),
  });
  const options = (data?.items ?? [])
    .filter((o) => o.id !== excludeId)
    .map((o) => ({
      value: String(o.id),
      label: `${o.operation_number} — ${o.finished_name}${o.client_name ? ` (${o.client_name})` : ""}`,
    }));
  if (value && !options.some((o) => o.value === String(value.id))) {
    options.unshift({ value: String(value.id), label: value.operation_number });
  }
  return (
    <Select
      label={f.ordenRelacionada}
      description={f.ordenRelacionadaHint}
      data={options}
      value={value ? String(value.id) : null}
      onChange={(v) => {
        selectedLabel.current = options.find((o) => o.value === v)?.label ?? null;
        onChange(v);
      }}
      searchable
      searchValue={search}
      onSearchChange={setSearch}
      filter={({ options: opts }) => opts}
      nothingFoundMessage={strings.common.sinDatos}
      required
    />
  );
}
