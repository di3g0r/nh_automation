import { Center, Stack, Text, Title } from "@mantine/core";

import { strings } from "../i18n/strings";

/** Placeholder for phase 3 (operator station). Operators land here after login. */
export function OperatorStationPage() {
  return (
    <Center h="80vh">
      <Stack align="center" gap="xs">
        <Title order={2}>{strings.operatorStation.title}</Title>
        <Text c="dimmed">{strings.operatorStation.placeholder}</Text>
      </Stack>
    </Center>
  );
}
