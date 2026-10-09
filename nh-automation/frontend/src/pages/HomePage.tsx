import { Stack, Text, Title } from "@mantine/core";

import { strings } from "../i18n/strings";

export function HomePage() {
  return (
    <Stack>
      <Title order={2}>{strings.home.title}</Title>
      <Text>{strings.home.bienvenida}</Text>
    </Stack>
  );
}
