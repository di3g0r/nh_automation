import { Alert, Button, CopyButton, Group, Modal, Stack, Table, Text } from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { IconAlertTriangle } from "@tabler/icons-react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { machinesApi } from "../../api/catalogs";
import type { Machine, PlcCredentials } from "../../api/types";
import { strings } from "../../i18n/strings";
import { formatAgo, formatDateTime } from "../../utils/datetime";
import { notifyError } from "../../utils/notify";

const t = strings.catalogs.machines;

/**
 * Phase 4: create the machine's PLC database login, or rotate its password.
 * The password is shown exactly once, with the connection data for the PLC
 * programmer (machines.plc_credentials, master admin only).
 */
export function PlcCredentialsModal({
  machine,
  onClose,
}: {
  machine: Machine | null;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const [result, setResult] = useState<PlcCredentials | null>(null);
  const mutation = useMutation({
    mutationFn: (id: number) => machinesApi.plcCredentials(id),
    onSuccess: (res) => {
      setResult(res);
      notifications.show({
        color: "green",
        message: res.created ? t.accesoCreado : t.accesoRotado,
      });
      queryClient.invalidateQueries({ queryKey: ["machines"] });
    },
    onError: notifyError,
  });
  const close = () => {
    setResult(null);
    onClose();
  };
  const hasLogin = !!machine?.plc_db_username;

  return (
    <Modal
      opened={machine !== null}
      onClose={close}
      title={t.credencialesPlc}
      closeOnClickOutside={result === null}
      size="lg"
    >
      {machine && !result && (
        <Stack>
          <Text fw={500}>
            {machine.code} — {machine.name}
          </Text>
          <Table>
            <Table.Tbody>
              <Table.Tr>
                <Table.Td>{t.plcUsuario}</Table.Td>
                <Table.Td>{machine.plc_db_username ?? t.sinPlc}</Table.Td>
              </Table.Tr>
              <Table.Tr>
                <Table.Td>{t.ultimoContacto}</Table.Td>
                <Table.Td>
                  {machine.last_seen_at
                    ? `${formatDateTime(machine.last_seen_at)} (${formatAgo(machine.last_seen_at)})`
                    : "—"}
                </Table.Td>
              </Table.Tr>
            </Table.Tbody>
          </Table>
          <Text size="sm">{hasLogin ? t.rotarConfirm : t.crearConfirm}</Text>
          <Group justify="end">
            <Button variant="default" onClick={close}>
              {strings.common.cancelar}
            </Button>
            <Button
              color={hasLogin ? "orange" : "blue"}
              loading={mutation.isPending}
              onClick={() => mutation.mutate(machine.id)}
            >
              {hasLogin ? t.rotarAcceso : t.crearAcceso}
            </Button>
          </Group>
        </Stack>
      )}
      {result && (
        <Stack>
          <Text fw={500}>
            {result.machine.code} — {result.machine.name}
          </Text>
          <Alert color="orange" icon={<IconAlertTriangle size={16} />}>
            {t.passwordWarning}
          </Alert>
          <Table>
            <Table.Tbody>
              <Row label={t.servidor} value={result.host || t.servidorSinConfigurar} />
              <Row label={t.puerto} value={String(result.port)} />
              <Row label={t.baseDatos} value={result.database} />
              <Row label={t.usuario} value={result.username} />
              <Row label={t.contrasena} value={result.password} mono />
            </Table.Tbody>
          </Table>
          <Group justify="end">
            <CopyButton value={result.password}>
              {({ copied, copy }) => (
                <Button variant="light" color={copied ? "teal" : "blue"} onClick={copy}>
                  {copied ? t.copiada : `${t.copiar} ${t.contrasena.toLowerCase()}`}
                </Button>
              )}
            </CopyButton>
            <Button onClick={close}>{t.entendido}</Button>
          </Group>
        </Stack>
      )}
    </Modal>
  );
}

function Row({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <Table.Tr>
      <Table.Td>{label}</Table.Td>
      <Table.Td ff={mono ? "monospace" : undefined} style={{ wordBreak: "break-all" }}>
        {value}
      </Table.Td>
    </Table.Tr>
  );
}
