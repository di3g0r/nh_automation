import {
  ActionIcon,
  Alert,
  Button,
  Center,
  Group,
  Loader,
  Modal,
  Select,
  Stack,
  Text,
  TextInput,
} from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { IconPlus, IconTrash } from "@tabler/icons-react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { ordersApi } from "../../api/orders";
import { productionApi } from "../../api/production";
import type { MachineBoardItem, Order } from "../../api/types";
import { strings } from "../../i18n/strings";
import { formatLiters } from "../../utils/datetime";
import { notifyError } from "../../utils/notify";
import { splitSummary } from "../../utils/production";
import { useInvalidateProduction } from "./useInvalidateProduction";

const t = strings.production.asignar;

interface Row {
  key: number;
  machineId: string | null;
  liters: string;
}

/** FR-ASG-1/2: split the order across one or more machines (BR-7). */
export function AssignMachinesModal({
  orderId,
  onClose,
}: {
  orderId: number;
  onClose: () => void;
}) {
  const { data: order } = useQuery({
    queryKey: ["orders", orderId],
    queryFn: () => ordersApi.get(orderId),
  });
  const { data: board } = useQuery({
    queryKey: ["machines-board"],
    queryFn: productionApi.board,
  });
  return (
    <Modal opened onClose={onClose} title={t.titulo} size="lg">
      {order && board ? (
        <AssignForm order={order} board={board} onClose={onClose} />
      ) : (
        <Center h={120}>
          <Loader />
        </Center>
      )}
    </Modal>
  );
}

function initialRows(order: Order): Row[] {
  const live = order.assignments.filter((a) => a.status !== "cancelled");
  if (live.length) {
    return live.map((a, i) => ({
      key: i,
      machineId: String(a.machine_id),
      liters: a.planned_liters,
    }));
  }
  return [{ key: 0, machineId: null, liters: Number(order.finished_liters).toFixed(2) }];
}

function AssignForm({
  order,
  board,
  onClose,
}: {
  order: Order;
  board: MachineBoardItem[];
  onClose: () => void;
}) {
  const invalidate = useInvalidateProduction();
  const [rows, setRows] = useState<Row[]>(() => initialRows(order));
  const [nextKey, setNextKey] = useState(100);
  const byId = new Map(board.map((m) => [String(m.id), m]));
  const ownMachines = new Set(order.assignments.map((a) => String(a.machine_id)));
  const summary = splitSummary(
    rows.map((r) => r.liters),
    order.finished_liters,
  );
  const complete = rows.every((r) => r.machineId && Number(r.liters) > 0);
  const mutation = useMutation({
    mutationFn: (split: Row[]) =>
      productionApi.setAssignments(
        order.id,
        split.map((r) => ({ machine_id: Number(r.machineId), planned_liters: r.liters.trim() })),
      ),
    onSuccess: (_d, split) => {
      notifications.show({ color: "green", message: split.length ? t.guardado : t.quitadas });
      invalidate();
      onClose();
    },
    onError: notifyError,
  });

  if (!order.can_assign) return <Alert color="gray">{t.bloqueado}</Alert>;

  const update = (key: number, patch: Partial<Row>) =>
    setRows((rs) => rs.map((r) => (r.key === key ? { ...r, ...patch } : r)));
  const chosen = new Set(rows.map((r) => r.machineId));
  const remaining = Number(summary.remaining);

  return (
    <Stack>
      <Text size="sm" c="dimmed">
        {order.operation_number} · {order.finished_name} · {formatLiters(order.finished_liters)}
      </Text>
      {rows.map((row) => {
        const machine = row.machineId ? byId.get(row.machineId) : undefined;
        // Busy machines are allowed: the order queues (FR-ASG-1). This order's own
        // pending assignment on the machine does not count as "others in the queue".
        const ownPending = ownMachines.has(row.machineId ?? "") ? 1 : 0;
        const queued = machine && (machine.state !== "free" || machine.queue_length > ownPending);
        return (
          <Stack key={row.key} gap={2}>
            <Group align="end" wrap="nowrap">
              <Select
                label={t.maquina}
                style={{ flex: 2 }}
                value={row.machineId}
                onChange={(v) => update(row.key, { machineId: v })}
                data={board.map((m) => ({
                  value: String(m.id),
                  label: `${m.code} — ${strings.machines.estados[m.state]} · ${m.queue_length} ${t.enFila}`,
                  disabled:
                    m.state === "maintenance" ||
                    (chosen.has(String(m.id)) && row.machineId !== String(m.id)),
                }))}
              />
              <TextInput
                label={t.litros}
                style={{ flex: 1 }}
                value={row.liters}
                onChange={(e) =>
                  update(row.key, { liters: e.currentTarget.value.replace(",", ".") })
                }
                rightSection="L"
                inputMode="decimal"
              />
              <ActionIcon
                variant="subtle"
                color="red"
                size="lg"
                aria-label={t.quitar}
                onClick={() => setRows((rs) => rs.filter((r) => r.key !== row.key))}
              >
                <IconTrash size={18} />
              </ActionIcon>
            </Group>
            {queued && (
              <Text size="xs" c="orange">
                {t.avisoOcupada}
              </Text>
            )}
          </Stack>
        );
      })}
      <Group justify="space-between">
        <Button
          variant="light"
          leftSection={<IconPlus size={16} />}
          onClick={() => {
            setRows((rs) => [
              ...rs,
              { key: nextKey, machineId: null, liters: remaining > 0 ? summary.remaining : "" },
            ]);
            setNextKey((k) => k + 1);
          }}
        >
          {t.agregar}
        </Button>
        <Text fw={600} c={summary.exact ? "teal" : "red"}>
          {t.asignado} {formatLiters(summary.assigned)} / {formatLiters(order.finished_liters)}
          {!summary.exact &&
            remaining !== 0 &&
            ` — ${remaining > 0 ? t.faltan : t.sobran} ${formatLiters(Math.abs(remaining))}`}
        </Text>
      </Group>
      {!summary.exact && rows.length > 0 && (
        <Text size="xs" c="dimmed">
          {t.exacto}
        </Text>
      )}
      <Group justify="space-between">
        {order.assignments.some((a) => a.status !== "cancelled") ? (
          <Button
            variant="subtle"
            color="red"
            onClick={() => mutation.mutate([])}
            loading={mutation.isPending}
          >
            {t.quitarTodas}
          </Button>
        ) : (
          <span />
        )}
        <Group>
          <Button variant="default" onClick={onClose}>
            {strings.common.cancelar}
          </Button>
          <Button
            disabled={!summary.exact || !complete || rows.length === 0}
            loading={mutation.isPending}
            onClick={() => mutation.mutate(rows)}
          >
            {strings.common.guardar}
          </Button>
        </Group>
      </Group>
    </Stack>
  );
}
