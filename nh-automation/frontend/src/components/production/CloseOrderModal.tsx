import { Alert, Button, Group, List, Modal, Stack, Table, Text, Textarea } from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { useMutation } from "@tanstack/react-query";
import { useState } from "react";

import { productionApi } from "../../api/production";
import type { Order } from "../../api/types";
import { strings } from "../../i18n/strings";
import { formatLiters } from "../../utils/datetime";
import { notifyError } from "../../utils/notify";
import { DifferenceText } from "./ProductionBadges";
import { useInvalidateProduction } from "./useInvalidateProduction";

const t = strings.production;

/**
 * BR-11: review and close a completed order. Allowed with any difference and
 * with incomplete checklist/lot/materials; the dialog lists what is missing.
 */
export function CloseOrderModal({ order, onClose }: { order: Order; onClose: () => void }) {
  const invalidate = useInvalidateProduction();
  const [note, setNote] = useState("");
  const mutation = useMutation({
    mutationFn: () => productionApi.close(order.id, note.trim() || null),
    onSuccess: () => {
      notifications.show({ color: "green", message: t.cerrar.cerrada });
      invalidate();
      onClose();
    },
    onError: notifyError,
  });
  const diff = order.difference;
  const live = order.assignments.filter((a) => a.status !== "cancelled");
  return (
    <Modal
      opened
      onClose={onClose}
      title={`${t.cerrar.titulo} ${order.operation_number}`}
      size="lg"
    >
      <Stack>
        {diff && (
          <Group gap="xl">
            <Text size="sm">
              {t.ordenado}: <b>{formatLiters(diff.ordered_liters)}</b>
            </Text>
            <Text size="sm">
              {t.real}: <b>{formatLiters(diff.actual_liters)}</b>
            </Text>
            <Group gap={4}>
              <Text size="sm">{t.diferencia}:</Text>
              <DifferenceText difference={diff} />
            </Group>
          </Group>
        )}
        {diff && !diff.within_range && <Alert color="red">{t.cerrar.fuera}</Alert>}
        <Table withTableBorder>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>{t.maquina}</Table.Th>
              <Table.Th ta="right">{t.planeado}</Table.Th>
              <Table.Th ta="right">{t.real}</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {live.map((a) => (
              <Table.Tr key={a.id}>
                <Table.Td>{a.machine_code}</Table.Td>
                <Table.Td ta="right">{formatLiters(a.planned_liters)}</Table.Td>
                <Table.Td ta="right">
                  {a.actual_liters === null ? "—" : formatLiters(a.actual_liters)}
                </Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
        {order.close_missing.length > 0 ? (
          <Alert color="orange" title={t.cerrar.faltantes}>
            <List size="sm">
              {order.close_missing.map((m) => (
                <List.Item key={m}>{t.cerrar.missing[m]}</List.Item>
              ))}
            </List>
          </Alert>
        ) : (
          <Text size="sm" c="teal">
            {t.cerrar.completa}
          </Text>
        )}
        <Textarea
          label={t.cerrar.nota}
          value={note}
          onChange={(e) => setNote(e.currentTarget.value)}
          autosize
          minRows={2}
          maxLength={2000}
        />
        <Group justify="flex-end">
          <Button variant="default" onClick={onClose}>
            {strings.common.cancelar}
          </Button>
          <Button onClick={() => mutation.mutate()} loading={mutation.isPending}>
            {t.cerrar.confirmar}
          </Button>
        </Group>
      </Stack>
    </Modal>
  );
}
