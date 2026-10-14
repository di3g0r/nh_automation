import { Alert, Button, Group, Modal, Stack, Text, TextInput, Tooltip } from "@mantine/core";
import { notifications } from "@mantine/notifications";
import {
  IconCheck,
  IconPlayerPause,
  IconPlayerPlay,
  IconPlayerTrackNext,
} from "@tabler/icons-react";
import { useMutation } from "@tanstack/react-query";
import { useState } from "react";

import { productionApi } from "../../api/production";
import type { Assignment } from "../../api/types";
import { useAuth } from "../../context/AuthContext";
import { strings } from "../../i18n/strings";
import { formatLiters } from "../../utils/datetime";
import { notifyError } from "../../utils/notify";
import { useInvalidateProduction } from "./useInvalidateProduction";

const t = strings.production;

type Action = "start" | "pause" | "resume";

/**
 * FR-PRD-1: Iniciar / Pausar / Reanudar / Terminar for one assignment, for
 * users with production.control (fallback to the PLC; recorded as "manual").
 */
export function AssignmentActions({
  assignment,
  size = "xs",
}: {
  assignment: Assignment;
  size?: string;
}) {
  const { hasPermission } = useAuth();
  const invalidate = useInvalidateProduction();
  const [completing, setCompleting] = useState(false);
  const mutation = useMutation({
    mutationFn: (action: Action) => productionApi[action](assignment.id),
    onSuccess: (_data, action) => {
      notifications.show({ color: "green", message: t.accionOk[action] });
      invalidate();
    },
    onError: (err) => {
      notifyError(err);
      invalidate();
    },
  });

  if (!hasPermission("production.control")) return null;
  const a = assignment;
  const busy = mutation.isPending;
  return (
    <Group gap={6} wrap="nowrap">
      {a.status === "pending" && (
        <Tooltip
          label={a.start_blocked_reason}
          disabled={!a.start_blocked_reason}
          multiline
          w={260}
        >
          <span>
            <Button
              size={size}
              color="green"
              leftSection={<IconPlayerPlay size={14} />}
              disabled={!a.can_start}
              loading={busy}
              onClick={() => mutation.mutate("start")}
            >
              {t.botones.iniciar}
            </Button>
          </span>
        </Tooltip>
      )}
      {a.can_pause && (
        <Button
          size={size}
          color="orange"
          variant="light"
          leftSection={<IconPlayerPause size={14} />}
          loading={busy}
          onClick={() => mutation.mutate("pause")}
        >
          {t.botones.pausar}
        </Button>
      )}
      {a.status === "paused" && (
        <Button
          size={size}
          color="green"
          variant="light"
          leftSection={<IconPlayerTrackNext size={14} />}
          disabled={!a.can_resume}
          loading={busy}
          onClick={() => mutation.mutate("resume")}
        >
          {t.botones.reanudar}
        </Button>
      )}
      {a.can_complete && (
        <Button
          size={size}
          color="teal"
          leftSection={<IconCheck size={14} />}
          disabled={busy}
          onClick={() => setCompleting(true)}
        >
          {t.botones.terminar}
        </Button>
      )}
      {completing && <CompleteModal assignment={a} onClose={() => setCompleting(false)} />}
    </Group>
  );
}

const LITERS_RE = /^\d+(\.\d{1,2})?$/;

/** Confirmation for Terminar: planned vs entered actual liters. */
function CompleteModal({ assignment, onClose }: { assignment: Assignment; onClose: () => void }) {
  const invalidate = useInvalidateProduction();
  const [liters, setLiters] = useState(
    assignment.actual_liters ?? Number(assignment.planned_liters).toFixed(2),
  );
  const valid = LITERS_RE.test(liters.trim());
  const mutation = useMutation({
    mutationFn: () => productionApi.complete(assignment.id, liters.trim()),
    onSuccess: () => {
      notifications.show({ color: "green", message: t.accionOk.complete });
      invalidate();
      onClose();
    },
    onError: notifyError,
  });
  return (
    <Modal
      opened
      onClose={onClose}
      title={`${t.terminar.titulo} — ${assignment.operation_number} · ${assignment.machine_code}`}
    >
      <Stack>
        <Text size="sm">
          {t.terminar.planeados}: <b>{formatLiters(assignment.planned_liters)}</b>
        </Text>
        <TextInput
          label={t.terminar.reales}
          value={liters}
          onChange={(e) => setLiters(e.currentTarget.value.replace(",", "."))}
          rightSection="L"
          inputMode="decimal"
          error={liters && !valid ? t.terminar.invalido : undefined}
          data-autofocus
        />
        {valid && (
          <Text size="sm">
            {t.real}: <b>{formatLiters(liters)}</b>
          </Text>
        )}
        <Alert color="blue" variant="light">
          {t.terminar.aviso}
        </Alert>
        <Group justify="flex-end">
          <Button variant="default" onClick={onClose}>
            {strings.common.cancelar}
          </Button>
          <Button
            color="teal"
            onClick={() => mutation.mutate()}
            loading={mutation.isPending}
            disabled={!valid}
          >
            {t.terminar.confirmar}
          </Button>
        </Group>
      </Stack>
    </Modal>
  );
}
