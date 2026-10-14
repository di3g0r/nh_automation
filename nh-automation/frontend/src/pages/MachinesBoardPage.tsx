import {
  ActionIcon,
  Anchor,
  Button,
  Card,
  Center,
  Group,
  Loader,
  Modal,
  Progress,
  SimpleGrid,
  Stack,
  Switch,
  Table,
  Text,
  Title,
  Tooltip,
} from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { IconArrowDown, IconArrowUp, IconListNumbers } from "@tabler/icons-react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";

import { machinesApi } from "../api/catalogs";
import { productionApi } from "../api/production";
import type { Assignment, MachineBoardItem } from "../api/types";
import { OrderTypeBadge } from "../components/orders/OrderBadges";
import { AssignmentActions } from "../components/production/AssignmentActions";
import {
  AssignmentStatusBadge,
  MachineStateBadge,
} from "../components/production/ProductionBadges";
import { useInvalidateProduction } from "../components/production/useInvalidateProduction";
import { useAuth } from "../context/AuthContext";
import { strings } from "../i18n/strings";
import { formatLiters } from "../utils/datetime";
import { notifyError } from "../utils/notify";
import { progressPercent } from "../utils/production";

const t = strings.machines;
const REFRESH_MS = 5_000; // FR-MCH-2

/** FR-MCH-1/2: one card per active machine, auto-refresh every 5 s. */
export function MachinesBoardPage() {
  const { data, isLoading } = useQuery({
    queryKey: ["machines-board"],
    queryFn: productionApi.board,
    refetchInterval: REFRESH_MS,
  });
  const [queueFor, setQueueFor] = useState<MachineBoardItem | null>(null);

  return (
    <Stack>
      <Group justify="space-between">
        <Title order={2}>{t.title}</Title>
        <Text size="xs" c="dimmed">
          {t.autoRefresh}
        </Text>
      </Group>
      {isLoading && (
        <Center h={200}>
          <Loader />
        </Center>
      )}
      {data?.length === 0 && <Text c="dimmed">{t.sinMaquinas}</Text>}
      <SimpleGrid cols={{ base: 1, sm: 2, lg: 3 }}>
        {data?.map((m) => (
          <MachineCard key={m.id} machine={m} onQueue={() => setQueueFor(m)} />
        ))}
      </SimpleGrid>
      {queueFor && <QueueModal machine={queueFor} onClose={() => setQueueFor(null)} />}
    </Stack>
  );
}

function OrderLine({ a }: { a: Assignment }) {
  return (
    <Group gap={6} wrap="nowrap">
      <Anchor component={Link} to={`/ordenes/${a.order_id}`} fw={600}>
        {a.operation_number}
      </Anchor>
      <OrderTypeBadge type={a.order_type} size="xs" />
    </Group>
  );
}

function MachineCard({ machine, onQueue }: { machine: MachineBoardItem; onQueue: () => void }) {
  const { hasPermission } = useAuth();
  const invalidate = useInvalidateProduction();
  const maintenance = useMutation({
    mutationFn: (on: boolean) => machinesApi.update(machine.id, { in_maintenance: on }),
    onSuccess: (_d, on) => {
      notifications.show({ color: "green", message: on ? t.mantenimientoOn : t.mantenimientoOff });
      invalidate();
    },
    onError: notifyError,
  });
  const current = machine.current;
  const next = machine.next_assignment;
  return (
    <Card withBorder padding="md">
      <Group justify="space-between" mb="xs">
        <div>
          <Title order={4}>{machine.code}</Title>
          <Text size="xs" c="dimmed">
            {machine.name} · {machine.site_name}
          </Text>
        </div>
        <MachineStateBadge state={machine.state} size="lg" />
      </Group>

      <Text size="xs" c="dimmed">
        {t.ordenActual}
      </Text>
      {current ? (
        <Stack gap={4} mb="sm">
          <Group justify="space-between">
            <OrderLine a={current} />
            <AssignmentStatusBadge status={current.status} />
          </Group>
          <Text size="sm">
            {current.finished_code} — {current.finished_name}
          </Text>
          <Progress value={progressPercent(current.actual_liters, current.planned_liters)} />
          <Text size="xs" c="dimmed">
            {formatLiters(current.actual_liters ?? 0)} / {formatLiters(current.planned_liters)}
          </Text>
          <AssignmentActions assignment={current} />
        </Stack>
      ) : (
        <Text size="sm" mb="sm">
          {t.sinOrden}
        </Text>
      )}

      {next && !current && (
        <Stack gap={4} mb="sm">
          <Text size="xs" c="dimmed">
            {t.siguiente}
          </Text>
          <Group justify="space-between">
            <OrderLine a={next} />
            <Text size="sm">{formatLiters(next.planned_liters)}</Text>
          </Group>
          <AssignmentActions assignment={next} />
        </Stack>
      )}

      <Group justify="space-between" mt="auto">
        <Button
          size="xs"
          variant="subtle"
          leftSection={<IconListNumbers size={14} />}
          onClick={onQueue}
        >
          {t.enFila}: {machine.queue_length}
        </Button>
        {hasPermission("catalogs.manage") && (
          <Switch
            size="sm"
            label={t.mantenimiento}
            checked={machine.in_maintenance}
            disabled={maintenance.isPending}
            onChange={(e) => maintenance.mutate(e.currentTarget.checked)}
          />
        )}
      </Group>
    </Card>
  );
}

/** FR-ASG-3: the machine's queue; orders.assign can reorder pending assignments. */
function QueueModal({ machine, onClose }: { machine: MachineBoardItem; onClose: () => void }) {
  const { hasPermission } = useAuth();
  const invalidate = useInvalidateProduction();
  const { data } = useQuery({
    queryKey: ["machine-queue", machine.id],
    queryFn: () => productionApi.queue(machine.id),
  });
  const reorder = useMutation({
    mutationFn: ({ id, position }: { id: number; position: number }) =>
      productionApi.reorder(id, position),
    onSuccess: () => {
      notifications.show({ color: "green", message: t.filaActualizada });
      invalidate();
    },
    onError: notifyError,
  });
  const canReorder = hasPermission("orders.assign");
  return (
    <Modal opened onClose={onClose} title={`${t.fila} ${machine.code}`} size="lg">
      {!data ? (
        <Loader />
      ) : (
        <Stack>
          {data.current && (
            <Group justify="space-between">
              <OrderLine a={data.current} />
              <AssignmentStatusBadge status={data.current.status} />
            </Group>
          )}
          {data.pending.length === 0 ? (
            <Text c="dimmed">{t.filaVacia}</Text>
          ) : (
            <Table>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>{t.posicion}</Table.Th>
                  <Table.Th>{strings.orders.columnas.numero}</Table.Th>
                  <Table.Th>{strings.orders.columnas.estado}</Table.Th>
                  <Table.Th ta="right">{strings.production.planeado}</Table.Th>
                  {canReorder && <Table.Th />}
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {data.pending.map((a, i) => (
                  <Table.Tr key={a.id}>
                    <Table.Td>{i + 1}</Table.Td>
                    <Table.Td>
                      <OrderLine a={a} />
                      {a.start_blocked_reason && (
                        <Text size="xs" c="dimmed">
                          {a.start_blocked_reason}
                        </Text>
                      )}
                    </Table.Td>
                    <Table.Td>{strings.orders.estados[a.order_status]}</Table.Td>
                    <Table.Td ta="right">{formatLiters(a.planned_liters)}</Table.Td>
                    {canReorder && (
                      <Table.Td>
                        <Group gap={4} wrap="nowrap">
                          <Tooltip label={t.subir}>
                            <ActionIcon
                              variant="subtle"
                              disabled={i === 0 || reorder.isPending}
                              onClick={() => reorder.mutate({ id: a.id, position: i })}
                              aria-label={t.subir}
                            >
                              <IconArrowUp size={16} />
                            </ActionIcon>
                          </Tooltip>
                          <Tooltip label={t.bajar}>
                            <ActionIcon
                              variant="subtle"
                              disabled={i === data.pending.length - 1 || reorder.isPending}
                              onClick={() => reorder.mutate({ id: a.id, position: i + 2 })}
                              aria-label={t.bajar}
                            >
                              <IconArrowDown size={16} />
                            </ActionIcon>
                          </Tooltip>
                        </Group>
                      </Table.Td>
                    )}
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          )}
        </Stack>
      )}
    </Modal>
  );
}
