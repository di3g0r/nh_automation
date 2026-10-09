import { Alert, Button, Code, CopyButton, Group, Modal, Stack, Text } from "@mantine/core";
import { IconAlertTriangle } from "@tabler/icons-react";

import type { MachineWithKey } from "../../api/types";
import { strings } from "../../i18n/strings";

const t = strings.catalogs.machines;

/** FR-CAT-5: the API key is shown exactly once, right after creation/rotation. */
export function MachineKeyModal({
  data,
  onClose,
}: {
  data: MachineWithKey | null;
  onClose: () => void;
}) {
  return (
    <Modal
      opened={data !== null}
      onClose={onClose}
      title={t.keyTitle}
      closeOnClickOutside={false}
      size="lg"
    >
      {data && (
        <Stack>
          <Text fw={500}>
            {data.machine.code} — {data.machine.name}
          </Text>
          <Alert color="orange" icon={<IconAlertTriangle size={16} />}>
            {t.keyWarning}
          </Alert>
          <Code block style={{ wordBreak: "break-all" }}>
            {data.api_key}
          </Code>
          <Group justify="end">
            <CopyButton value={data.api_key}>
              {({ copied, copy }) => (
                <Button variant="light" color={copied ? "teal" : "blue"} onClick={copy}>
                  {copied ? t.copiada : t.copiar}
                </Button>
              )}
            </CopyButton>
            <Button onClick={onClose}>{t.entendido}</Button>
          </Group>
        </Stack>
      )}
    </Modal>
  );
}
