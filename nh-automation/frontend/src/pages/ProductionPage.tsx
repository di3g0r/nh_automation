import {
  Anchor,
  Badge,
  Button,
  Group,
  Loader,
  Paper,
  Stack,
  Table,
  Text,
  Title,
} from "@mantine/core";
import { IconCalendar, IconEngine, IconEye } from "@tabler/icons-react";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import type { ReactNode } from "react";
import { Link, useNavigate } from "react-router-dom";

import { productionApi } from "../api/production";
import type { ProductionOrder } from "../api/types";
import { OrderStatusBadge, OrderTypeBadge } from "../components/orders/OrderBadges";
import { AssignMachinesModal } from "../components/production/AssignMachinesModal";
import { AssignmentsTable } from "../components/production/AssignmentsTable";
import { ExpiryModal } from "../components/production/ExpiryModal";
import { DifferenceText } from "../components/production/ProductionBadges";
import { useAuth } from "../context/AuthContext";
import { strings } from "../i18n/strings";
import { formatLiters } from "../utils/datetime";
import { formatExpiry } from "../utils/orders";

const t = strings.production;
const REFRESH_MS = 10_000; // FR-PM-1

/** FR-PM-1: the Production manager's home — Por asignar, En producción, Por cerrar. */
export function ProductionPage() {
  const toAssign = useQuery({
    queryKey: ["production", "to-assign"],
    queryFn: productionApi.toAssign,
    refetchInterval: REFRESH_MS,
  });
  const inProduction = useQuery({
    queryKey: ["production", "in-production"],
    queryFn: productionApi.inProduction,
    refetchInterval: REFRESH_MS,
  });
  const toClose = useQuery({
    queryKey: ["production", "to-close"],
    queryFn: productionApi.toClose,
    refetchInterval: REFRESH_MS,
  });
  const [expiryFor, setExpiryFor] = useState<number | null>(null);
  const [assignFor, setAssignFor] = useState<number | null>(null);

  return (
    <Stack>
      <Group justify="space-between">
        <Title order={2}>{t.title}</Title>
        <Text size="xs" c="dimmed">
          {t.autoRefresh}
        </Text>
      </Group>

      <Section title={t.porAsignar} count={toAssign.data?.length} loading={toAssign.isLoading}>
        {toAssign.data && (
          <ToAssignTable orders={toAssign.data} onExpiry={setExpiryFor} onAssign={setAssignFor} />
        )}
      </Section>

      <Section
        title={t.enProduccion}
        count={inProduction.data?.length}
        loading={inProduction.isLoading}
      >
        {inProduction.data?.length === 0 && <Text c="dimmed">{t.sinOrdenes}</Text>}
        <Stack gap="sm">
          {inProduction.data?.map((o) => (
            <InProductionCard key={o.id} order={o} onAssign={setAssignFor} />
          ))}
        </Stack>
      </Section>

      <Section title={t.porCerrar} count={toClose.data?.length} loading={toClose.isLoading}>
        {toClose.data && <ToCloseTable orders={toClose.data} />}
      </Section>

      {expiryFor !== null && <ExpiryModal orderId={expiryFor} onClose={() => setExpiryFor(null)} />}
      {assignFor !== null && (
        <AssignMachinesModal orderId={assignFor} onClose={() => setAssignFor(null)} />
      )}
    </Stack>
  );
}

function Section({
  title,
  count,
  loading,
  children,
}: {
  title: string;
  count: number | undefined;
  loading: boolean;
  children: ReactNode;
}) {
  return (
    <Paper withBorder p="md">
      <Group mb="sm" gap="xs">
        <Title order={4}>{title}</Title>
        {count !== undefined && (
          <Badge variant="light" color="gray">
            {count}
          </Badge>
        )}
      </Group>
      {loading ? <Loader size="sm" /> : children}
    </Paper>
  );
}

function OrderLink({ order }: { order: ProductionOrder }) {
  return (
    <Group gap={6} wrap="nowrap">
      <Anchor component={Link} to={`/ordenes/${order.id}`} fw={600}>
        {order.operation_number}
      </Anchor>
      <OrderTypeBadge type={order.order_type} size="sm" />
    </Group>
  );
}

function ToAssignTable({
  orders,
  onExpiry,
  onAssign,
}: {
  orders: ProductionOrder[];
  onExpiry: (id: number) => void;
  onAssign: (id: number) => void;
}) {
  const { hasPermission } = useAuth();
  if (!orders.length) return <Text c="dimmed">{t.sinOrdenes}</Text>;
  return (
    <Table.ScrollContainer minWidth={800}>
      <Table striped>
        <Table.Thead>
          <Table.Tr>
            <Table.Th>{strings.orders.columnas.numero}</Table.Th>
            <Table.Th>{strings.orders.columnas.cliente}</Table.Th>
            <Table.Th>{strings.orders.columnas.productoTerminado}</Table.Th>
            <Table.Th ta="right">{strings.orders.columnas.litros}</Table.Th>
            <Table.Th>{t.caducidad}</Table.Th>
            <Table.Th />
            <Table.Th />
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {orders.map((o) => (
            <Table.Tr key={o.id}>
              <Table.Td>
                <OrderLink order={o} />
              </Table.Td>
              <Table.Td>{o.client_name ?? strings.orders.form.sinCliente}</Table.Td>
              <Table.Td>
                {o.finished_code} — {o.finished_name}
              </Table.Td>
              <Table.Td ta="right">{formatLiters(o.finished_liters)}</Table.Td>
              <Table.Td>{o.expiry_date ? formatExpiry(o.expiry_date) : "—"}</Table.Td>
              <Table.Td>
                <Group gap={4}>
                  {o.missing.map((m) => (
                    <Badge key={m} color="orange" variant="light" size="sm">
                      {t.missing[m]}
                    </Badge>
                  ))}
                </Group>
              </Table.Td>
              <Table.Td>
                <Group gap={6} wrap="nowrap" justify="flex-end">
                  {hasPermission("orders.expiry") && (
                    <Button
                      size="xs"
                      variant={o.missing.includes("expiry") ? "filled" : "light"}
                      leftSection={<IconCalendar size={14} />}
                      onClick={() => onExpiry(o.id)}
                    >
                      {t.asignarCaducidad}
                    </Button>
                  )}
                  {hasPermission("orders.assign") && (
                    <Button
                      size="xs"
                      variant={o.missing.includes("machines") ? "filled" : "light"}
                      leftSection={<IconEngine size={14} />}
                      onClick={() => onAssign(o.id)}
                    >
                      {t.asignarMaquinas}
                    </Button>
                  )}
                </Group>
              </Table.Td>
            </Table.Tr>
          ))}
        </Table.Tbody>
      </Table>
    </Table.ScrollContainer>
  );
}

function InProductionCard({
  order,
  onAssign,
}: {
  order: ProductionOrder;
  onAssign: (id: number) => void;
}) {
  const { hasPermission } = useAuth();
  return (
    <Paper withBorder p="sm" bg="gray.0">
      <Group justify="space-between" mb={4}>
        <Group gap="sm">
          <OrderLink order={order} />
          <OrderStatusBadge status={order.status} size="sm" />
          <Text size="sm">
            {order.finished_code} — {order.finished_name} · {formatLiters(order.finished_liters)}
          </Text>
          {order.expiry_date && (
            <Text size="sm" c="dimmed">
              {t.caducidad} {formatExpiry(order.expiry_date)}
            </Text>
          )}
        </Group>
        {order.status === "assigned" && hasPermission("orders.assign") && (
          <Button
            size="xs"
            variant="subtle"
            leftSection={<IconEngine size={14} />}
            onClick={() => onAssign(order.id)}
          >
            {t.asignarMaquinas}
          </Button>
        )}
      </Group>
      <AssignmentsTable assignments={order.assignments} />
    </Paper>
  );
}

function ToCloseTable({ orders }: { orders: ProductionOrder[] }) {
  const navigate = useNavigate();
  if (!orders.length) return <Text c="dimmed">{t.sinOrdenes}</Text>;
  return (
    <Table.ScrollContainer minWidth={700}>
      <Table striped>
        <Table.Thead>
          <Table.Tr>
            <Table.Th>{strings.orders.columnas.numero}</Table.Th>
            <Table.Th>{strings.orders.columnas.productoTerminado}</Table.Th>
            <Table.Th ta="right">{t.ordenado}</Table.Th>
            <Table.Th ta="right">{t.real}</Table.Th>
            <Table.Th>{t.diferencia}</Table.Th>
            <Table.Th />
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {orders.map((o) => (
            <Table.Tr key={o.id}>
              <Table.Td>
                <OrderLink order={o} />
              </Table.Td>
              <Table.Td>
                {o.finished_code} — {o.finished_name}
              </Table.Td>
              <Table.Td ta="right">{formatLiters(o.finished_liters)}</Table.Td>
              <Table.Td ta="right">
                {o.difference ? formatLiters(o.difference.actual_liters) : "—"}
              </Table.Td>
              <Table.Td>{o.difference && <DifferenceText difference={o.difference} />}</Table.Td>
              <Table.Td>
                <Group justify="flex-end">
                  <Button
                    size="xs"
                    leftSection={<IconEye size={14} />}
                    onClick={() => navigate(`/ordenes/${o.id}?tab=maquinas`)}
                  >
                    {t.revisarCerrar}
                  </Button>
                </Group>
              </Table.Td>
            </Table.Tr>
          ))}
        </Table.Tbody>
      </Table>
    </Table.ScrollContainer>
  );
}
