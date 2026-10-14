import { Center, Stack, Text, Title } from "@mantine/core";

import { strings } from "../i18n/strings";

/** Placeholder for phase 3 (Production manager queue). The Production manager lands here. */
export function ProductionPage() {
  return (
    <Center h="80vh">
      <Stack align="center" gap="xs">
        <Title order={2}>{strings.production.title}</Title>
        <Text c="dimmed" ta="center">
          {strings.production.placeholder}
        </Text>
      </Stack>
    </Center>
  );
}
