import { Badge, Table, Text } from "@mantine/core";

import type { Assignment } from "../../api/types";
import { strings } from "../../i18n/strings";
import { formatDateTime, formatLiters } from "../../utils/datetime";
import { AssignmentActions } from "./AssignmentActions";
import { AssignmentStatusBadge } from "./ProductionBadges";

const t = strings.production;

/** Per-machine status, liters and production controls of one order. */
export function AssignmentsTable({
  assignments,
  showTimes = false,
}: {
  assignments: Assignment[];
  showTimes?: boolean;
}) {
  if (!assignments.length) {
    return (
      <Text size="sm" c="dimmed">
        {strings.orders.detalle.sinAsignaciones}
      </Text>
    );
  }
  return (
    <Table.ScrollContainer minWidth={600}>
      <Table verticalSpacing={4}>
        <Table.Thead>
          <Table.Tr>
            <Table.Th>{t.maquina}</Table.Th>
            <Table.Th>{t.estado}</Table.Th>
            <Table.Th ta="right">{t.planeado}</Table.Th>
            <Table.Th ta="right">{t.real}</Table.Th>
            {showTimes && <Table.Th>{t.origen}</Table.Th>}
            <Table.Th>{t.acciones}</Table.Th>
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {assignments.map((a) => (
            <Table.Tr key={a.id}>
              <Table.Td>
                <Text size="sm" fw={600}>
                  {a.machine_code}
                </Text>
                {showTimes && a.started_at && (
                  <Text size="xs" c="dimmed">
                    {formatDateTime(a.started_at)}
                    {a.completed_at && ` → ${formatDateTime(a.completed_at)}`}
                  </Text>
                )}
              </Table.Td>
              <Table.Td>
                <AssignmentStatusBadge status={a.status} />
              </Table.Td>
              <Table.Td ta="right">{formatLiters(a.planned_liters)}</Table.Td>
              <Table.Td ta="right">
                {a.actual_liters === null ? "—" : formatLiters(a.actual_liters)}
              </Table.Td>
              {showTimes && (
                <Table.Td>
                  {a.last_source ? (
                    <Badge variant="outline" size="sm" color="gray">
                      {t.fuentes[a.last_source]}
                    </Badge>
                  ) : (
                    "—"
                  )}
                </Table.Td>
              )}
              <Table.Td>
                <AssignmentActions assignment={a} />
              </Table.Td>
            </Table.Tr>
          ))}
        </Table.Tbody>
      </Table>
    </Table.ScrollContainer>
  );
}
