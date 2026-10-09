import { Group, Table, Text, TextInput, Title, Stack, Code } from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { auditApi } from "../api/audit";
import { strings } from "../i18n/strings";
import { formatDateTime } from "../utils/datetime";

export function AuditLogPage() {
  const [entity, setEntity] = useState("");
  const [page, setPage] = useState(1);

  const { data, isLoading } = useQuery({
    queryKey: ["audit", entity, page],
    queryFn: () => auditApi.list({ entity: entity || undefined, page, page_size: 25 }),
  });

  return (
    <Stack>
      <Title order={2}>{strings.audit.title}</Title>

      <Group>
        <TextInput
          label={strings.audit.filtros.entidad}
          placeholder="user"
          value={entity}
          onChange={(e) => {
            setPage(1);
            setEntity(e.currentTarget.value);
          }}
        />
      </Group>

      <Table striped highlightOnHover>
        <Table.Thead>
          <Table.Tr>
            <Table.Th>{strings.audit.columnas.fecha}</Table.Th>
            <Table.Th>{strings.audit.columnas.usuario}</Table.Th>
            <Table.Th>{strings.audit.columnas.entidad}</Table.Th>
            <Table.Th>{strings.audit.columnas.id}</Table.Th>
            <Table.Th>{strings.audit.columnas.accion}</Table.Th>
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {!isLoading && data?.items.length === 0 && (
            <Table.Tr>
              <Table.Td colSpan={5}>
                <Text c="dimmed">{strings.common.sinDatos}</Text>
              </Table.Td>
            </Table.Tr>
          )}
          {data?.items.map((entry) => (
            <Table.Tr key={entry.id}>
              <Table.Td>{formatDateTime(entry.created_at)}</Table.Td>
              <Table.Td>{entry.user_id ?? strings.audit.sinUsuario}</Table.Td>
              <Table.Td>
                <Code>{entry.entity}</Code>
              </Table.Td>
              <Table.Td>{entry.entity_id ?? "-"}</Table.Td>
              <Table.Td>{entry.action}</Table.Td>
            </Table.Tr>
          ))}
        </Table.Tbody>
      </Table>

      {data && data.total > 25 && (
        <Group justify="center">
          <Text size="sm" c="dimmed">
            {strings.common.pagina} {page} {strings.common.de} {Math.ceil(data.total / 25)}
          </Text>
        </Group>
      )}
    </Stack>
  );
}
