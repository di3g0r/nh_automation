import { Alert, Button, Center, Group, Loader, Modal, Select, Stack, Text } from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { ordersApi } from "../../api/orders";
import { productionApi } from "../../api/production";
import type { Order } from "../../api/types";
import { strings } from "../../i18n/strings";
import { formatExpiry, localToday } from "../../utils/orders";
import { notifyError } from "../../utils/notify";
import { expiryFromParts, expiryParts, expiryYears } from "../../utils/production";
import { useInvalidateProduction } from "./useInvalidateProduction";

const t = strings.production.caducidadModal;
const MONTHS = Array.from({ length: 12 }, (_, i) => {
  const v = String(i + 1).padStart(2, "0");
  return { value: v, label: v };
});

/** FR-PM-2: month/year picker, shown MM/AAAA (BR-20). Loads the order by id. */
export function ExpiryModal({ orderId, onClose }: { orderId: number; onClose: () => void }) {
  const { data: order } = useQuery({
    queryKey: ["orders", orderId],
    queryFn: () => ordersApi.get(orderId),
  });
  return (
    <Modal opened onClose={onClose} title={t.titulo}>
      {order ? (
        <ExpiryForm order={order} onClose={onClose} />
      ) : (
        <Center h={120}>
          <Loader />
        </Center>
      )}
    </Modal>
  );
}

function ExpiryForm({ order, onClose }: { order: Order; onClose: () => void }) {
  const invalidate = useInvalidateProduction();
  const initial = expiryParts(order.expiry_date);
  const [month, setMonth] = useState<string | null>(initial.month);
  const [year, setYear] = useState<string | null>(initial.year);
  const [confirming, setConfirming] = useState(false);
  const value = expiryFromParts(month, year);
  // Retrabajo de inventario propio: entered once, then locked -> confirm first.
  const needsConfirm = order.rework_kind === "own_stock";
  const mutation = useMutation({
    mutationFn: (v: string | null) => productionApi.setExpiry(order.id, v),
    onSuccess: (_d, v) => {
      notifications.show({ color: "green", message: v ? t.guardada : t.quitada });
      invalidate();
      onClose();
    },
    onError: notifyError,
  });

  if (!order.can_set_expiry) {
    return (
      <Stack>
        <Alert color="gray">
          {order.expiry_locked ? t.bloqueada : strings.production.asignar.bloqueado}
        </Alert>
        {order.expiry_date && <Text>{formatExpiry(order.expiry_date)}</Text>}
      </Stack>
    );
  }
  if (confirming && value) {
    return (
      <Stack>
        <Alert color="orange">{t.avisoRetrabajo}</Alert>
        <Text fw={600}>{formatExpiry(value)}</Text>
        <Group justify="flex-end">
          <Button variant="default" onClick={() => setConfirming(false)}>
            {strings.common.cancelar}
          </Button>
          <Button onClick={() => mutation.mutate(value)} loading={mutation.isPending}>
            {t.confirmar}
          </Button>
        </Group>
      </Stack>
    );
  }
  return (
    <Stack>
      <Text size="sm" c="dimmed">
        {order.operation_number} · {order.finished_name}
      </Text>
      <Group grow>
        <Select label={t.mes} data={MONTHS} value={month} onChange={setMonth} data-autofocus />
        <Select label={t.anio} data={expiryYears(localToday())} value={year} onChange={setYear} />
      </Group>
      {needsConfirm && <Alert color="orange">{t.avisoRetrabajo}</Alert>}
      <Group justify="space-between">
        {order.order_type === "trabajo" && order.expiry_date ? (
          <Button
            variant="subtle"
            color="red"
            onClick={() => mutation.mutate(null)}
            loading={mutation.isPending}
          >
            {t.quitar}
          </Button>
        ) : (
          <span />
        )}
        <Group>
          <Button variant="default" onClick={onClose}>
            {strings.common.cancelar}
          </Button>
          <Button
            disabled={!value}
            loading={mutation.isPending}
            onClick={() => (needsConfirm ? setConfirming(true) : mutation.mutate(value))}
          >
            {t.guardar}
          </Button>
        </Group>
      </Group>
    </Stack>
  );
}
