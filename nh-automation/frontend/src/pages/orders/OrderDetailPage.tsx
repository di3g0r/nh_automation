import {
  Alert,
  Anchor,
  Button,
  Center,
  Checkbox,
  Grid,
  Group,
  Loader,
  Modal,
  Paper,
  Stack,
  Table,
  Tabs,
  Text,
  TextInput,
  Textarea,
  Title,
} from "@mantine/core";
import { notifications } from "@mantine/notifications";
import {
  IconAlertTriangle,
  IconArrowLeft,
  IconBan,
  IconCalendar,
  IconEdit,
  IconEngine,
  IconLock,
  IconPrinter,
  IconTrash,
} from "@tabler/icons-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import type { ReactNode } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";

import { ordersApi } from "../../api/orders";
import { productionApi } from "../../api/production";
import type {
  ChecklistItem,
  Order,
  OrderHistoryEntry,
  PackagingShortageWarning,
} from "../../api/types";
import { OrderStatusBadge, OrderTypeBadge } from "../../components/orders/OrderBadges";
import { AssignMachinesModal } from "../../components/production/AssignMachinesModal";
import { AssignmentsTable } from "../../components/production/AssignmentsTable";
import { CloseOrderModal } from "../../components/production/CloseOrderModal";
import { ExpiryModal } from "../../components/production/ExpiryModal";
import { DifferenceText } from "../../components/production/ProductionBadges";
import { useInvalidateProduction } from "../../components/production/useInvalidateProduction";
import { useAuth } from "../../context/AuthContext";
import { strings } from "../../i18n/strings";
import { formatDateTime, formatLiters } from "../../utils/datetime";
import { errorMessage, notifyError } from "../../utils/notify";
import { changedKeys, formatExpiry, formatHistoryValue, formatPlainDate } from "../../utils/orders";
import { formatUnits } from "../../utils/quantity";

const t = strings.orders;
const f = t.form;
const d = t.detalle;
const pr = strings.production;
const TABS = ["informacion", "maquinas", "materiales", "checklist", "comentarios", "historial"];

/** FR-ORD-3: `/ordenes/:id`, tabs + actions by status and permission. */
export function OrderDetailPage() {
  const { id } = useParams();
  const orderId = Number(id);
  const navigate = useNavigate();
  const { hasPermission } = useAuth();
  const [searchParams] = useSearchParams();
  const initialTab = searchParams.get("tab");
  const [cancelOpen, setCancelOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [expiryOpen, setExpiryOpen] = useState(false);
  const [assignOpen, setAssignOpen] = useState(false);
  const [closeOpen, setCloseOpen] = useState(false);
  const { data: order, error } = useQuery({
    queryKey: ["orders", orderId],
    queryFn: () => ordersApi.get(orderId),
  });

  if (error) {
    return (
      <Stack>
        <Alert color="red">{errorMessage(error)}</Alert>
        <Anchor component={Link} to="/ordenes">
          {d.volver}
        </Anchor>
      </Stack>
    );
  }
  if (!order) {
    return (
      <Center h="50vh">
        <Loader />
      </Center>
    );
  }

  const canEdit = order.can_edit && hasPermission("orders.edit");
  const canCancel = order.can_cancel && hasPermission("orders.cancel");
  const canDelete = order.can_delete && hasPermission("orders.edit");
  const canExpiry = order.can_set_expiry && hasPermission("orders.expiry");
  const canAssign = order.can_assign && hasPermission("orders.assign");
  const canClose = order.can_close && hasPermission("orders.close");

  return (
    <Stack maw={1100}>
      <Anchor component={Link} to="/ordenes" size="sm">
        <Group gap={4}>
          <IconArrowLeft size={14} />
          {t.title}
        </Group>
      </Anchor>
      <Group justify="space-between" align="start">
        <Group>
          <Title order={2}>{order.operation_number}</Title>
          <OrderTypeBadge type={order.order_type} size="lg" />
          <OrderStatusBadge status={order.status} size="lg" />
        </Group>
        <Group>
          {canExpiry && (
            <Button
              variant={order.expiry_date ? "light" : "filled"}
              leftSection={<IconCalendar size={16} />}
              onClick={() => setExpiryOpen(true)}
            >
              {pr.asignarCaducidad}
            </Button>
          )}
          {canAssign && (
            <Button
              variant={order.missing_for_assign.includes("machines") ? "filled" : "light"}
              leftSection={<IconEngine size={16} />}
              onClick={() => setAssignOpen(true)}
            >
              {pr.asignarMaquinas}
            </Button>
          )}
          {canClose && (
            <Button
              color="teal"
              leftSection={<IconLock size={16} />}
              onClick={() => setCloseOpen(true)}
            >
              {pr.cerrarOrden}
            </Button>
          )}
          {canEdit && (
            <Button
              leftSection={<IconEdit size={16} />}
              onClick={() => navigate(`/ordenes/${order.id}/editar`)}
            >
              {d.editar}
            </Button>
          )}
          <Button
            variant="light"
            leftSection={<IconPrinter size={16} />}
            onClick={() => navigate(`/ordenes/${order.id}/imprimir`)}
          >
            {d.imprimir}
          </Button>
          {canCancel && (
            <Button
              variant="light"
              color="orange"
              leftSection={<IconBan size={16} />}
              onClick={() => setCancelOpen(true)}
            >
              {d.cancelarOrden}
            </Button>
          )}
          {canDelete && (
            <Button
              variant="light"
              color="red"
              leftSection={<IconTrash size={16} />}
              onClick={() => setDeleteOpen(true)}
            >
              {d.eliminar}
            </Button>
          )}
        </Group>
      </Group>

      {order.status === "cancelled" && (
        <Alert color="red" icon={<IconBan />}>
          {d.canceladaPor} {order.cancelled_by_name} · {formatDateTime(order.cancelled_at)}
          <br />
          {d.motivoCancelacion}: {order.cancel_reason}
        </Alert>
      )}
      {order.status === "created" && order.missing_for_assign.length > 0 && (
        <Alert color="blue" variant="light">
          <Group gap="xs">
            {order.missing_for_assign.map((m) => (
              <Text key={m} size="sm" fw={500}>
                {pr.missing[m]}
              </Text>
            ))}
          </Group>
        </Alert>
      )}
      {order.difference && (
        <Alert color={order.difference.within_range ? "teal" : "red"} variant="light">
          <Group gap="xl">
            <Text size="sm">
              {pr.ordenado}: <b>{formatLiters(order.difference.ordered_liters)}</b>
            </Text>
            <Text size="sm">
              {pr.real}: <b>{formatLiters(order.difference.actual_liters)}</b>
            </Text>
            <Group gap={4}>
              <Text size="sm">{pr.diferencia}:</Text>
              <DifferenceText difference={order.difference} />
            </Group>
          </Group>
        </Alert>
      )}
      {order.status === "closed" && order.close_note && (
        <Alert color="gray" icon={<IconLock />}>
          {d.notaCierre}: {order.close_note}
        </Alert>
      )}
      {order.warnings.length > 0 && (order.status === "created" || order.status === "assigned") && (
        <Alert color="orange" icon={<IconAlertTriangle />} title={f.avisoEmpaque}>
          {order.warnings.map((w) => (
            <Text key={w.packaging_item_id} size="sm">
              {w.code} — {w.description}: {d.planeado} {formatUnits(w.planned)},{" "}
              {strings.alerts.disponible} {formatUnits(w.available)}
            </Text>
          ))}
        </Alert>
      )}

      <Tabs
        defaultValue={initialTab && TABS.includes(initialTab) ? initialTab : "informacion"}
        keepMounted={false}
      >
        <Tabs.List>
          <Tabs.Tab value="informacion">{d.tabs.informacion}</Tabs.Tab>
          <Tabs.Tab value="maquinas">{d.tabs.maquinas}</Tabs.Tab>
          <Tabs.Tab value="materiales">{d.tabs.materiales}</Tabs.Tab>
          <Tabs.Tab value="checklist">{d.tabs.checklist}</Tabs.Tab>
          <Tabs.Tab value="comentarios">{d.tabs.comentarios}</Tabs.Tab>
          <Tabs.Tab value="historial">{d.tabs.historial}</Tabs.Tab>
        </Tabs.List>
        <Tabs.Panel value="informacion" pt="md">
          <InfoTab order={order} />
        </Tabs.Panel>
        <Tabs.Panel value="maquinas" pt="md">
          <MachinesTab order={order} />
        </Tabs.Panel>
        <Tabs.Panel value="materiales" pt="md">
          <MaterialsTab order={order} />
        </Tabs.Panel>
        <Tabs.Panel value="checklist" pt="md">
          <ChecklistTab order={order} />
        </Tabs.Panel>
        <Tabs.Panel value="comentarios" pt="md">
          <CommentsTab orderId={order.id} canComment={hasPermission("orders.comment")} />
        </Tabs.Panel>
        <Tabs.Panel value="historial" pt="md">
          <HistoryTab order={order} />
        </Tabs.Panel>
      </Tabs>

      {cancelOpen && <CancelModal order={order} onClose={() => setCancelOpen(false)} />}
      {deleteOpen && <DeleteModal order={order} onClose={() => setDeleteOpen(false)} />}
      {expiryOpen && <ExpiryModal orderId={order.id} onClose={() => setExpiryOpen(false)} />}
      {assignOpen && (
        <AssignMachinesModal orderId={order.id} onClose={() => setAssignOpen(false)} />
      )}
      {closeOpen && <CloseOrderModal order={order} onClose={() => setCloseOpen(false)} />}
    </Stack>
  );
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div>
      <Text size="xs" c="dimmed">
        {label}
      </Text>
      <Text size="sm" fw={500}>
        {children || "—"}
      </Text>
    </div>
  );
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <Paper withBorder p="md">
      <Title order={5} mb="sm">
        {title}
      </Title>
      {children}
    </Paper>
  );
}

function InfoTab({ order }: { order: Order }) {
  const expiry = order.expiry_date ? formatExpiry(order.expiry_date) : f.caducidadPendiente;
  return (
    <Stack>
      <Section title={f.secciones.general}>
        <Grid>
          {order.rework_kind && (
            <Grid.Col span={{ base: 12, sm: 4 }}>
              <Field label={f.tipoRetrabajo}>{t.reworkKinds[order.rework_kind]}</Field>
            </Grid.Col>
          )}
          {order.related_order_id && (
            <Grid.Col span={{ base: 12, sm: 4 }}>
              <Field label={f.ordenRelacionada}>
                <Anchor component={Link} to={`/ordenes/${order.related_order_id}`}>
                  {order.related_operation_number}
                </Anchor>
              </Field>
            </Grid.Col>
          )}
          <Grid.Col span={{ base: 12, sm: 4 }}>
            <Field label={f.cliente}>{order.client_name ?? f.sinCliente}</Field>
          </Grid.Col>
          <Grid.Col span={{ base: 12, sm: 4 }}>
            <Field label={f.razonSocial}>
              {order.razon_social_code} — {order.razon_social_name}
            </Field>
          </Grid.Col>
          <Grid.Col span={{ base: 12, sm: 4 }}>
            <Field label={f.lugar}>{order.site_name}</Field>
          </Grid.Col>
          <Grid.Col span={{ base: 12, sm: 4 }}>
            <Field label={f.fecha}>{formatPlainDate(order.order_date)}</Field>
          </Grid.Col>
          <Grid.Col span={{ base: 12, sm: 4 }}>
            <Field label={d.creadaPor}>
              {order.created_by_name} · {formatDateTime(order.created_at)}
            </Field>
          </Grid.Col>
          {order.closed_by_name && (
            <Grid.Col span={{ base: 12, sm: 4 }}>
              <Field label={d.cerradaPor}>
                {order.closed_by_name} · {formatDateTime(order.closed_at)}
              </Field>
            </Grid.Col>
          )}
        </Grid>
      </Section>

      <Section title={f.secciones.base}>
        <Table>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>{t.print.codigo}</Table.Th>
              <Table.Th>{t.print.nombre}</Table.Th>
              <Table.Th>{t.print.proveedor}</Table.Th>
              <Table.Th>{t.print.presentacion}</Table.Th>
              <Table.Th>{f.razonSocial}</Table.Th>
              <Table.Th ta="right">{f.litros}</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {order.base_products.map((b) => (
              <Table.Tr key={b.position}>
                <Table.Td>{b.code}</Table.Td>
                <Table.Td>{b.name}</Table.Td>
                <Table.Td>{b.provider}</Table.Td>
                <Table.Td>{b.presentation}</Table.Td>
                <Table.Td>{b.razon_social_code}</Table.Td>
                <Table.Td ta="right">{formatLiters(b.liters)}</Table.Td>
              </Table.Tr>
            ))}
            <Table.Tr>
              <Table.Td colSpan={5} fw={600}>
                {f.totalBase}
              </Table.Td>
              <Table.Td ta="right" fw={600}>
                {formatLiters(order.base_liters_total)}
              </Table.Td>
            </Table.Tr>
          </Table.Tbody>
        </Table>
      </Section>

      <Section title={f.secciones.terminado}>
        <Grid>
          <Grid.Col span={{ base: 12, sm: 3 }}>
            <Field label={t.print.codigo}>{order.finished_code}</Field>
          </Grid.Col>
          <Grid.Col span={{ base: 12, sm: 5 }}>
            <Field label={t.print.nombre}>{order.finished_name}</Field>
          </Grid.Col>
          <Grid.Col span={{ base: 12, sm: 2 }}>
            <Field label={t.print.presentacion}>{order.finished_presentation}</Field>
          </Grid.Col>
          <Grid.Col span={{ base: 12, sm: 2 }}>
            <Field label={f.litros}>{formatLiters(order.finished_liters)}</Field>
          </Grid.Col>
        </Grid>
      </Section>

      <Section title={f.secciones.trazabilidad}>
        <Grid>
          <Grid.Col span={{ base: 12, sm: 4 }}>
            <Field label={d.loteAnterior}>{order.previous_lot}</Field>
          </Grid.Col>
          <Grid.Col span={{ base: 12, sm: 4 }}>
            <Field label={d.lotePosterior}>{order.new_lot}</Field>
          </Grid.Col>
          <Grid.Col span={{ base: 12, sm: 4 }}>
            <Field label={f.caducidad}>{expiry}</Field>
            {order.expiry_set_by_name && (
              <Text size="xs" c="dimmed">
                {d.caducidadPor} {order.expiry_set_by_name} · {formatDateTime(order.expiry_set_at)}
              </Text>
            )}
          </Grid.Col>
        </Grid>
      </Section>
    </Stack>
  );
}

/** Máquinas tab: split, per-machine status and the production controls. */
function MachinesTab({ order }: { order: Order }) {
  const live = order.assignments.filter((a) => a.status !== "cancelled");
  return (
    <Stack>
      <Text size="sm">
        {d.asignadoTotal}: <b>{formatLiters(order.assigned_liters)}</b> /{" "}
        {formatLiters(order.finished_liters)}
      </Text>
      <AssignmentsTable assignments={live.length ? live : order.assignments} showTimes />
    </Stack>
  );
}

function MaterialsTab({ order }: { order: Order }) {
  const { hasPermission } = useAuth();
  if (order.can_edit_traceability && hasPermission("orders.traceability")) {
    return <MaterialsForm order={order} />;
  }
  return (
    <Stack>
      {order.status === "closed" && (
        <Text size="sm" c="dimmed">
          {d.soloLectura}
        </Text>
      )}
      {order.packaging.length === 0 ? (
        <Text c="dimmed">{d.sinMaterial}</Text>
      ) : (
        <Table striped>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>{t.print.codigo}</Table.Th>
              <Table.Th>{f.material}</Table.Th>
              <Table.Th ta="right">{d.planeado}</Table.Th>
              <Table.Th ta="right">{d.real}</Table.Th>
              <Table.Th>{d.registradoPor}</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {order.packaging.map((p) => (
              <Table.Tr key={p.packaging_item_id}>
                <Table.Td>{p.code}</Table.Td>
                <Table.Td>{p.description}</Table.Td>
                <Table.Td ta="right">{formatUnits(p.planned_qty)}</Table.Td>
                <Table.Td ta="right">
                  {p.actual_qty === null ? "—" : formatUnits(p.actual_qty)}
                </Table.Td>
                <Table.Td>
                  {p.actual_by_name ? `${p.actual_by_name} · ${formatDateTime(p.actual_at)}` : "—"}
                </Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      )}
      <Grid>
        <Grid.Col span={{ base: 12, sm: 4 }}>
          <Field label={`${d.etiquetas} — ${d.planeado}`}>
            {order.labels_planned === null ? "" : formatUnits(order.labels_planned)}
          </Field>
        </Grid.Col>
        <Grid.Col span={{ base: 12, sm: 4 }}>
          <Field label={`${d.etiquetas} — ${d.real}`}>
            {order.labels_actual === null ? "" : formatUnits(order.labels_actual)}
          </Field>
        </Grid.Col>
        <Grid.Col span={{ base: 12, sm: 4 }}>
          <Field label={f.codigoBarras}>{t.barcodeModes[order.barcode_mode]}</Field>
        </Grid.Col>
      </Grid>
    </Stack>
  );
}

const INT_RE = /^\d+$/;

/** BR-24: actual packaging and labels, prefilled with the planned values. */
function MaterialsForm({ order }: { order: Order }) {
  const invalidate = useInvalidateProduction();
  const [qty, setQty] = useState<Record<number, string>>(() =>
    Object.fromEntries(
      order.packaging.map((p) => [p.packaging_item_id, String(p.actual_qty ?? p.planned_qty)]),
    ),
  );
  const [labels, setLabels] = useState(
    order.labels_actual !== null
      ? String(order.labels_actual)
      : order.labels_planned !== null
        ? String(order.labels_planned)
        : "",
  );
  const valid =
    Object.values(qty).every((v) => INT_RE.test(v.trim())) &&
    (labels.trim() === "" || INT_RE.test(labels.trim()));
  const mutation = useMutation({
    mutationFn: () =>
      productionApi.materials(order.id, {
        packaging: order.packaging.map((p) => ({
          packaging_item_id: p.packaging_item_id,
          actual_qty: Number(qty[p.packaging_item_id]),
        })),
        labels_actual: labels.trim() === "" ? null : Number(labels),
      }),
    onSuccess: () => {
      notifications.show({ color: "green", message: d.materialesGuardados });
      invalidate();
    },
    onError: notifyError,
  });
  return (
    <Stack>
      <Text size="sm" c="dimmed">
        {d.materialesHint}
      </Text>
      {order.packaging.length === 0 ? (
        <Text c="dimmed">{d.sinMaterial}</Text>
      ) : (
        <Table striped>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>{t.print.codigo}</Table.Th>
              <Table.Th>{f.material}</Table.Th>
              <Table.Th ta="right">{d.planeado}</Table.Th>
              <Table.Th w={140}>{d.real}</Table.Th>
              <Table.Th>{d.registradoPor}</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {order.packaging.map((p) => (
              <Table.Tr key={p.packaging_item_id}>
                <Table.Td>{p.code}</Table.Td>
                <Table.Td>{p.description}</Table.Td>
                <Table.Td ta="right">{formatUnits(p.planned_qty)}</Table.Td>
                <Table.Td>
                  <TextInput
                    size="xs"
                    value={qty[p.packaging_item_id]}
                    inputMode="numeric"
                    aria-label={`${d.real} ${p.code}`}
                    onChange={(e) => {
                      const v = e.currentTarget.value;
                      setQty((q) => ({ ...q, [p.packaging_item_id]: v }));
                    }}
                    error={!INT_RE.test(qty[p.packaging_item_id].trim())}
                  />
                </Table.Td>
                <Table.Td>
                  {p.actual_by_name ? `${p.actual_by_name} · ${formatDateTime(p.actual_at)}` : "—"}
                </Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      )}
      <Grid align="end">
        <Grid.Col span={{ base: 12, sm: 4 }}>
          <Field label={`${d.etiquetas} — ${d.planeado}`}>
            {order.labels_planned === null ? "" : formatUnits(order.labels_planned)}
          </Field>
        </Grid.Col>
        <Grid.Col span={{ base: 12, sm: 4 }}>
          <TextInput
            label={`${d.etiquetas} — ${d.real}`}
            value={labels}
            inputMode="numeric"
            onChange={(e) => setLabels(e.currentTarget.value)}
            description={
              order.labels_actual_by_name
                ? `${order.labels_actual_by_name} · ${formatDateTime(order.labels_actual_at)}`
                : undefined
            }
          />
        </Grid.Col>
        <Grid.Col span={{ base: 12, sm: 4 }}>
          <Field label={f.codigoBarras}>{t.barcodeModes[order.barcode_mode]}</Field>
        </Grid.Col>
      </Grid>
      <Group justify="flex-end">
        <Button onClick={() => mutation.mutate()} loading={mutation.isPending} disabled={!valid}>
          {d.guardarMateriales}
        </Button>
      </Group>
    </Stack>
  );
}

/** Checklist (each change records who and when) and lots (BR-24). */
function ChecklistTab({ order }: { order: Order }) {
  const { hasPermission } = useAuth();
  const invalidate = useInvalidateProduction();
  const editable = order.can_edit_traceability && hasPermission("orders.traceability");
  const toggle = useMutation({
    mutationFn: ({ item, checked }: { item: ChecklistItem; checked: boolean }) =>
      productionApi.checklist(order.id, [{ item, checked }]),
    onSuccess: () => {
      notifications.show({ color: "green", message: d.checklistGuardado });
      invalidate();
    },
    onError: notifyError,
  });
  return (
    <Stack>
      <Text size="sm" c="dimmed">
        {editable ? d.checklistPendiente : order.status === "closed" ? d.soloLectura : ""}
      </Text>
      {order.checklist.map((c) => (
        <Group key={c.item} justify="space-between" maw={600}>
          <Checkbox
            checked={c.checked}
            readOnly={!editable}
            disabled={toggle.isPending}
            label={t.checklist[c.item]}
            onChange={(e) =>
              editable && toggle.mutate({ item: c.item, checked: e.currentTarget.checked })
            }
          />
          {c.checked_by_name && (
            <Text size="xs" c="dimmed">
              {c.checked_by_name} · {formatDateTime(c.checked_at)}
            </Text>
          )}
        </Group>
      ))}
      <LotsSection order={order} editable={editable} />
    </Stack>
  );
}

function LotsSection({ order, editable }: { order: Order; editable: boolean }) {
  const invalidate = useInvalidateProduction();
  const [newLot, setNewLot] = useState(order.new_lot ?? "");
  const [previousLot, setPreviousLot] = useState(order.previous_lot ?? "");
  const mutation = useMutation({
    mutationFn: () =>
      productionApi.traceability(order.id, {
        new_lot: newLot.trim() || null,
        previous_lot: previousLot.trim() || null,
      }),
    onSuccess: () => {
      notifications.show({ color: "green", message: d.lotesGuardados });
      invalidate();
    },
    onError: notifyError,
  });
  const changed =
    (newLot.trim() || null) !== order.new_lot ||
    (previousLot.trim() || null) !== order.previous_lot;
  return (
    <Section title={strings.orders.print.lotes}>
      <Grid align="end">
        <Grid.Col span={{ base: 12, sm: 4 }}>
          <TextInput
            label={d.loteAnterior}
            value={previousLot}
            maxLength={100}
            readOnly={!editable}
            onChange={(e) => setPreviousLot(e.currentTarget.value)}
          />
        </Grid.Col>
        <Grid.Col span={{ base: 12, sm: 4 }}>
          <TextInput
            label={d.lotePosterior}
            value={newLot}
            maxLength={100}
            readOnly={!editable}
            onChange={(e) => setNewLot(e.currentTarget.value)}
            description={
              order.new_lot_by_name
                ? `${order.new_lot_by_name} · ${formatDateTime(order.new_lot_at)}`
                : undefined
            }
          />
        </Grid.Col>
        {editable && (
          <Grid.Col span={{ base: 12, sm: 4 }}>
            <Button
              onClick={() => mutation.mutate()}
              loading={mutation.isPending}
              disabled={!changed}
            >
              {d.guardarLotes}
            </Button>
          </Grid.Col>
        )}
      </Grid>
    </Section>
  );
}

function CommentsTab({ orderId, canComment }: { orderId: number; canComment: boolean }) {
  const queryClient = useQueryClient();
  const [text, setText] = useState("");
  const { data: comments, isLoading } = useQuery({
    queryKey: ["orders", orderId, "comments"],
    queryFn: () => ordersApi.comments(orderId),
  });
  const mutation = useMutation({
    mutationFn: () => ordersApi.addComment(orderId, text.trim()),
    onSuccess: () => {
      setText("");
      queryClient.invalidateQueries({ queryKey: ["orders", orderId] });
      notifications.show({ color: "green", message: d.comentarioAgregado });
    },
    onError: notifyError,
  });

  return (
    <Stack maw={800}>
      {canComment && (
        <Stack gap="xs">
          <Textarea
            placeholder={d.comentarioPlaceholder}
            value={text}
            onChange={(e) => setText(e.currentTarget.value)}
            autosize
            minRows={2}
            maxLength={2000}
          />
          <Group justify="flex-end">
            <Button
              onClick={() => mutation.mutate()}
              loading={mutation.isPending}
              disabled={!text.trim()}
            >
              {d.agregarComentario}
            </Button>
          </Group>
        </Stack>
      )}
      {isLoading && <Loader size="sm" />}
      {comments?.length === 0 && <Text c="dimmed">{d.sinComentarios}</Text>}
      {comments?.map((c) => (
        <Paper key={c.id} withBorder p="sm">
          <Text size="xs" c="dimmed" mb={4}>
            {c.user_name} · {formatDateTime(c.created_at)}
          </Text>
          <Text size="sm" style={{ whiteSpace: "pre-wrap" }}>
            {c.text}
          </Text>
        </Paper>
      ))}
    </Stack>
  );
}

/** Snapshot keys not worth showing as a change (identity / derived). */
const HIDDEN_HISTORY_KEYS = new Set([
  "operation_number",
  "order_type",
  "razon_social_id",
  "finished_product_id",
  "comment_id",
  "released_reservations",
]);

/** Actions whose before/after hold the same keys: shown as "old → new". */
const DIFF_ACTIONS = new Set([
  "update",
  "assign",
  "expiry",
  "checklist",
  "traceability",
  "materials",
  "queue",
]);

function HistoryTab({ order }: { order: Order }) {
  const { data: entries, isLoading } = useQuery({
    queryKey: ["orders", order.id, "history"],
    queryFn: () => ordersApi.history(order.id),
  });
  const packagingCodes = new Map(order.packaging.map((p) => [p.packaging_item_id, p.code]));
  if (isLoading) return <Loader size="sm" />;
  if (!entries?.length) return <Text c="dimmed">{strings.common.sinDatos}</Text>;
  return (
    <Table striped>
      <Table.Thead>
        <Table.Tr>
          <Table.Th w={150}>{strings.audit.columnas.fecha}</Table.Th>
          <Table.Th w={180}>{strings.audit.columnas.usuario}</Table.Th>
          <Table.Th w={130}>{strings.audit.columnas.accion}</Table.Th>
          <Table.Th>{d.cambios}</Table.Th>
        </Table.Tr>
      </Table.Thead>
      <Table.Tbody>
        {entries.map((e) => (
          <Table.Tr key={e.id}>
            <Table.Td>{formatDateTime(e.created_at)}</Table.Td>
            <Table.Td>{e.user_name ?? strings.audit.sinUsuario}</Table.Td>
            <Table.Td>{d.acciones[e.action as keyof typeof d.acciones] ?? e.action}</Table.Td>
            <Table.Td>
              <HistoryChanges entry={e} packagingCodes={packagingCodes} />
            </Table.Td>
          </Table.Tr>
        ))}
      </Table.Tbody>
    </Table>
  );
}

function HistoryChanges({
  entry,
  packagingCodes,
}: {
  entry: OrderHistoryEntry;
  packagingCodes: Map<number, string>;
}) {
  const label = (k: string) => {
    if (k.startsWith("packaging_")) {
      return `${d.real} ${packagingCodes.get(Number(k.slice(10))) ?? k}`;
    }
    if (k in t.checklist) return t.checklist[k as ChecklistItem];
    return d.campos[k as keyof typeof d.campos] ?? k;
  };
  if (entry.action === "create") return <Text size="sm">—</Text>;
  if (entry.action === "comment") {
    return (
      <Text size="sm" style={{ whiteSpace: "pre-wrap" }}>
        {formatHistoryValue(entry.after?.text)}
      </Text>
    );
  }
  const isDiff = DIFF_ACTIONS.has(entry.action);
  const keys = isDiff ? changedKeys(entry.before, entry.after) : Object.keys(entry.after ?? {});
  const shown = keys.filter((k) => !HIDDEN_HISTORY_KEYS.has(k));
  if (!shown.length) return <Text size="sm">—</Text>;
  return (
    <Stack gap={2}>
      {shown.map((k) => (
        <Text key={k} size="sm">
          <b>{label(k)}:</b>{" "}
          {isDiff || k === "status"
            ? `${historyValue(k, entry.before?.[k], packagingCodes)} → ${historyValue(
                k,
                entry.after?.[k],
                packagingCodes,
              )}`
            : historyValue(k, entry.after?.[k], packagingCodes)}
        </Text>
      ))}
    </Stack>
  );
}

function historyValue(key: string, value: unknown, packagingCodes: Map<number, string>): string {
  if (key === "status" && typeof value === "string") {
    return t.estados[value as keyof typeof t.estados] ?? value;
  }
  if (key === "barcode_mode" && typeof value === "string") {
    return t.barcodeModes[value as keyof typeof t.barcodeModes] ?? value;
  }
  if (key === "rework_kind" && typeof value === "string") {
    return t.reworkKinds[value as keyof typeof t.reworkKinds] ?? value;
  }
  if (key === "order_date" && typeof value === "string") return formatPlainDate(value);
  if (key === "expiry_date" && typeof value === "string") return formatExpiry(value);
  if (key === "source" && typeof value === "string") {
    return pr.fuentes[value as keyof typeof pr.fuentes] ?? value;
  }
  if (typeof value === "boolean") return value ? t.print.si : "No";
  if (key === "missing" && Array.isArray(value)) {
    if (!value.length) return "—";
    return value
      .map((m) => pr.cerrar.missing[m as keyof typeof pr.cerrar.missing] ?? String(m))
      .join(", ");
  }
  if (key === "warnings" && Array.isArray(value)) {
    if (!value.length) return "—";
    return value
      .map((w) => {
        const { code, planned, available } = w as PackagingShortageWarning;
        return `${code} (${d.planeado.toLowerCase()} ${formatUnits(planned)}, ${
          strings.alerts.disponible
        } ${formatUnits(available)})`;
      })
      .join(", ");
  }
  return formatHistoryValue(value, packagingCodes);
}

function CancelModal({ order, onClose }: { order: Order; onClose: () => void }) {
  const queryClient = useQueryClient();
  const [reason, setReason] = useState("");
  const mutation = useMutation({
    mutationFn: () => ordersApi.cancel(order.id, reason.trim()),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["orders"] });
      queryClient.invalidateQueries({ queryKey: ["inventory"] });
      notifications.show({ color: "green", message: d.cancelada });
      onClose();
    },
    onError: notifyError,
  });
  return (
    <Modal opened onClose={onClose} title={`${d.cancelarOrden} ${order.operation_number}`}>
      <Stack>
        <Text size="sm">{d.confirmarCancelar}</Text>
        <Textarea
          label={d.motivo}
          required
          value={reason}
          onChange={(e) => setReason(e.currentTarget.value)}
          autosize
          minRows={2}
          maxLength={2000}
          data-autofocus
        />
        <Group justify="flex-end">
          <Button variant="default" onClick={onClose}>
            {strings.common.cerrar}
          </Button>
          <Button
            color="orange"
            onClick={() => mutation.mutate()}
            loading={mutation.isPending}
            disabled={!reason.trim()}
          >
            {d.cancelarOrden}
          </Button>
        </Group>
      </Stack>
    </Modal>
  );
}

function DeleteModal({ order, onClose }: { order: Order; onClose: () => void }) {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const mutation = useMutation({
    mutationFn: () => ordersApi.remove(order.id),
    onSuccess: () => {
      queryClient.removeQueries({ queryKey: ["orders", order.id] });
      queryClient.invalidateQueries({ queryKey: ["orders"] });
      queryClient.invalidateQueries({ queryKey: ["inventory"] });
      notifications.show({ color: "green", message: d.eliminada });
      navigate("/ordenes");
    },
    onError: notifyError,
  });
  return (
    <Modal opened onClose={onClose} title={`${d.eliminar} ${order.operation_number}`}>
      <Stack>
        <Text size="sm">{d.confirmarEliminar}</Text>
        <Group justify="flex-end">
          <Button variant="default" onClick={onClose}>
            {strings.common.cerrar}
          </Button>
          <Button color="red" onClick={() => mutation.mutate()} loading={mutation.isPending}>
            {d.eliminar}
          </Button>
        </Group>
      </Stack>
    </Modal>
  );
}
