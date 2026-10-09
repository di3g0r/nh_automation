import { Button, Checkbox, Group, NumberInput, Stack, Table, Title } from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { ApiError } from "../api/client";
import { settingsApi } from "../api/settings";
import { strings } from "../i18n/strings";

export function SettingsPage() {
  const queryClient = useQueryClient();
  const { data, isLoading } = useQuery({ queryKey: ["settings"], queryFn: settingsApi.list });
  const [edited, setEdited] = useState<Record<string, unknown>>({});

  const mutation = useMutation({
    mutationFn: (key: string) => settingsApi.update(key, edited[key]),
    onSuccess: () => {
      notifications.show({ message: strings.settings.actualizado, color: "green" });
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
    </Stack>
  );
}
