import { Badge, Group, Text, Tooltip } from "@mantine/core";
import { IconAlertTriangle } from "@tabler/icons-react";

import type { AssignmentStatus, Difference, MachineState } from "../../api/types";
import { strings } from "../../i18n/strings";
import { formatLiters } from "../../utils/datetime";
import { ASSIGNMENT_COLOR, MACHINE_STATE_COLOR, differenceKind } from "../../utils/production";

const t = strings.production;

export function AssignmentStatusBadge({ status }: { status: AssignmentStatus }) {
  return (
    <Badge variant="light" color={ASSIGNMENT_COLOR[status]}>
      {t.asignacion[status]}
    </Badge>
  );
}

export function MachineStateBadge({ state, size = "md" }: { state: MachineState; size?: string }) {
  return (
    <Badge variant="filled" size={size} color={MACHINE_STATE_COLOR[state]}>
      {strings.machines.estados[state]}
    </Badge>
  );
}

/** *Faltante 1.00 L* / *Excedente 2.00 L*; highlighted only outside the range (BR-12). */
export function DifferenceText({ difference }: { difference: Difference }) {
  const { kind, liters } = differenceKind(difference.difference);
  if (kind === "none") {
    return (
      <Text size="sm" c="teal" fw={500}>
        {t.sinDiferencia}
      </Text>
    );
  }
  const label = `${kind === "faltante" ? t.faltante : t.excedente} ${formatLiters(liters)}`;
  if (difference.within_range) {
    return <Text size="sm">{label}</Text>;
  }
  return (
    <Tooltip label={t.fueraDeRango}>
      <Group gap={4} wrap="nowrap">
        <IconAlertTriangle size={16} color="var(--mantine-color-red-6)" />
        <Text size="sm" c="red" fw={700}>
          {label}
        </Text>
      </Group>
    </Tooltip>
  );
}
