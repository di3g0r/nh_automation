import { Anchor, Badge, Card, Group, SimpleGrid, Stack, Text, Title } from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { ordersApi } from "../api/orders";
import { productionApi } from "../api/production";
import type { MachineState, OrderStatus } from "../api/types";
import { StockAlertsCard } from "../components/inventory/StockAlertsCard";
import { OrderStatusBadge } from "../components/orders/OrderBadges";
import { MachineStateBadge } from "../components/production/ProductionBadges";
import { useAuth } from "../context/AuthContext";
import { strings } from "../i18n/strings";
import { localToday } from "../utils/orders";

const t = strings.home;
const ORDER_STATUSES: OrderStatus[] = [
  "created",
  "assigned",
  "in_progress",
  "paused",
  "completed",
  "closed",
  "cancelled",
];
const MACHINE_STATES: MachineState[] = ["free", "busy", "paused", "maintenance"];

export function HomePage() {
  const { hasPermission } = useAuth();
  return (
    <Stack>
      <Title order={2}>{t.title}</Title>
      <Text>{t.bienvenida}</Text>
      <SimpleGrid cols={{ base: 1, md: 2 }}>
        {hasPermission("orders.view") && <TodayOrdersCard />}
        {hasPermission("machines.board") && <MachinesSummaryCard />}
      </SimpleGrid>
      {hasPermission("inventory.view") && <StockAlertsCard />}
    </Stack>
  );
}

/** Inicio: today's orders (local date, NFR-7a) by status. */
function TodayOrdersCard() {
  const { hasPermission } = useAuth();
  const today = localToday();
  const { data } = useQuery({
    queryKey: ["orders", "today", today],
    queryFn: () => ordersApi.list({ date_from: today, date_to: today, page_size: 500 }),
    refetchInterval: 30_000,
  });
  const counts = new Map<OrderStatus, number>();
  for (const o of data?.items ?? []) counts.set(o.status, (counts.get(o.status) ?? 0) + 1);
  return (
    <Card withBorder>
      <Group justify="space-between" mb="sm">
        <Title order={4}>{t.ordenesHoy}</Title>
        {hasPermission("orders.assign") && (
          <Anchor component={Link} to="/produccion" size="sm">
            {t.verProduccion}
          </Anchor>
        )}
      </Group>
      {data && data.total === 0 ? (
        <Text c="dimmed" size="sm">
          {t.sinOrdenesHoy}
        </Text>
      ) : (
        <Stack gap={6}>
          {ORDER_STATUSES.filter((s) => counts.get(s)).map((s) => (
            <Group key={s} justify="space-between">
              <OrderStatusBadge status={s} />
              <Text fw={600}>{counts.get(s)}</Text>
            </Group>
          ))}
          <Group justify="space-between">
            <Text size="sm" c="dimmed">
              {t.total}
            </Text>
            <Text fw={700}>{data?.total ?? "—"}</Text>
          </Group>
        </Stack>
      )}
    </Card>
  );
}

/** Inicio: machines by state. */
function MachinesSummaryCard() {
  const { data } = useQuery({
    queryKey: ["machines-board"],
    queryFn: productionApi.board,
    refetchInterval: 30_000,
  });
  return (
    <Card withBorder>
      <Group justify="space-between" mb="sm">
        <Title order={4}>{t.maquinas}</Title>
        <Anchor component={Link} to="/maquinas" size="sm">
          {t.verMaquinas}
        </Anchor>
      </Group>
      <Group gap="md">
        {MACHINE_STATES.map((s) => (
          <Group key={s} gap={6}>
            <MachineStateBadge state={s} />
            <Badge variant="outline" color="gray">
              {data ? data.filter((m) => m.state === s).length : "—"}
            </Badge>
          </Group>
        ))}
      </Group>
      <Stack gap={2} mt="sm">
        {data
          ?.filter((m) => m.current)
          .map((m) => (
            <Text key={m.id} size="sm">
              <b>{m.code}</b>: {m.current?.operation_number} · {m.current?.finished_name}
            </Text>
          ))}
      </Stack>
    </Card>
  );
}
