import {
  Alert,
  Button,
  Checkbox,
  Group,
  NumberInput,
  Stack,
  Table,
  Text,
  Title,
} from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { IconAlertTriangle } from "@tabler/icons-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { ApiError } from "../api/client";
import { sequencesApi, settingsApi } from "../api/settings";
import type { OrderSequence } from "../api/types";
import { useAuth } from "../context/AuthContext";
import { strings } from "../i18n/strings";
import { notifyError } from "../utils/notify";

/** Number inputs with limits; anything else is an unbounded number. */
const NUMBER_PROPS: Record<string, { min?: number; max?: number; decimalScale?: number }> = {
  difference_tolerance_liters: { min: 0, decimalScale: 2 },
  difference_tolerance_percent: { min: 0, max: 100, decimalScale: 2 },
};

export function SettingsPage() {
  const queryClient = useQueryClient();
  const { hasPermission } = useAuth();
  const { data, isLoading } = useQuery({ queryKey: ["settings"], queryFn: settingsApi.list });
  const [edited, setEdited] = useState<Record<string, unknown>>({});

  const mutation = useMutation({
    mutationFn: (key: string) => settingsApi.update(key, edited[key]),
    onSuccess: (_row, key) => {
      notifications.show({ message: strings.settings.actualizado, color: "green" });
      setEdited(({ [key]: _done, ...rest }) => rest);
      queryClient.invalidateQueries({ queryKey: ["settings"] });
    },
    onError: (err) =>
      notifications.show({
        message: err instanceof ApiError ? err.message : strings.common.errorGenerico,
        color: "red",
      }),
  });

  if (isLoading || !data) return null;

  return (
    <Stack>
      <Title order={2}>{strings.settings.title}</Title>
      <Table withTableBorder>
        <Table.Tbody>
          {data.map((setting) => {
            const label =
              strings.settings.claves[setting.key as keyof typeof strings.settings.claves] ??
              setting.key;
            const currentValue = setting.key in edited ? edited[setting.key] : setting.value;

            return (
              <Table.Tr key={setting.key}>
                <Table.Td w={360}>{label}</Table.Td>
                <Table.Td>
                  {typeof setting.value === "boolean" ? (
                    <Checkbox
                      checked={Boolean(currentValue)}
                      onChange={(e) =>
                        setEdited((prev) => ({ ...prev, [setting.key]: e.currentTarget.checked }))
                      }
                    />
                  ) : typeof setting.value === "number" ? (
                    <NumberInput
                      value={currentValue as number}
                      onChange={(v) => setEdited((prev) => ({ ...prev, [setting.key]: v }))}
                      w={160}
                      {...NUMBER_PROPS[setting.key]}
                    />
                  ) : (
                    <span>{String(currentValue ?? "")}</span>
                  )}
                </Table.Td>
                <Table.Td w={120}>
                  <Group justify="end">
                    <Button
                      size="xs"
                      disabled={!(setting.key in edited)}
                      loading={mutation.isPending}
                      onClick={() => mutation.mutate(setting.key)}
                    >
                      {strings.settings.guardar}
                    </Button>
                  </Group>
                </Table.Td>
              </Table.Tr>
            );
          })}
        </Table.Tbody>
      </Table>

      {hasPermission("sequences.manage") && <SequencesSection />}
    </Stack>
  );
}

/** Next Trabajo / Retrabajo number (master admin, `sequences.manage`). */
function SequencesSection() {
  const s = strings.settings.secuencias;
  const queryClient = useQueryClient();
  const { data } = useQuery({ queryKey: ["order-sequences"], queryFn: sequencesApi.list });
  const [edited, setEdited] = useState<Record<string, number | string>>({});

  const mutation = useMutation({
    mutationFn: (row: OrderSequence) =>
      sequencesApi.update(row.order_type, Number(edited[row.order_type])),
    onSuccess: (row) => {
      notifications.show({ message: s.actualizado, color: "green" });
      setEdited(({ [row.order_type]: _done, ...rest }) => rest);
      queryClient.invalidateQueries({ queryKey: ["order-sequences"] });
    },
    onError: notifyError,
  });

  return (
    <Stack gap="sm" mt="lg">
      <Title order={3}>{s.title}</Title>
      <Alert color="orange" icon={<IconAlertTriangle size={18} />}>
        {s.aviso}
      </Alert>
      <Table withTableBorder>
        <Table.Thead>
          <Table.Tr>
            <Table.Th>{s.tipo}</Table.Th>
            <Table.Th>{s.prefijo}</Table.Th>
            <Table.Th>{s.siguiente}</Table.Th>
            <Table.Th>{s.ejemplo}</Table.Th>
            <Table.Th w={120} />
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {data?.map((row) => {
            const value = edited[row.order_type] ?? row.next_number;
            const dirty = row.order_type in edited;
            const valid = Number.isInteger(Number(value)) && Number(value) >= 1;
            return (
              <Table.Tr key={row.order_type}>
                <Table.Td>{s.tipos[row.order_type]}</Table.Td>
                <Table.Td>{row.prefix}</Table.Td>
                <Table.Td>
                  <NumberInput
                    value={value}
                    min={1}
                    allowDecimal={false}
                    allowNegative={false}
                    onChange={(v) => setEdited((prev) => ({ ...prev, [row.order_type]: v }))}
                    w={160}
                  />
                </Table.Td>
                <Table.Td>
                  <Text c="dimmed">
                    {row.prefix}-{valid ? Number(value) : "?"}
                  </Text>
                </Table.Td>
                <Table.Td>
                  <Group justify="end">
                    <Button
                      size="xs"
                      disabled={!dirty || !valid}
                      loading={mutation.isPending}
                      onClick={() => mutation.mutate(row)}
                    >
                      {strings.settings.guardar}
                    </Button>
                  </Group>
                </Table.Td>
              </Table.Tr>
            );
          })}
        </Table.Tbody>
      </Table>
    </Stack>
  );
}
