import { Stack, Text, Title } from "@mantine/core";

import { StockAlertsCard } from "../components/inventory/StockAlertsCard";
import { useAuth } from "../context/AuthContext";
import { strings } from "../i18n/strings";

export function HomePage() {
  const { hasPermission } = useAuth();
  return (
    <Stack>
      <Title order={2}>{strings.home.title}</Title>
      <Text>{strings.home.bienvenida}</Text>
      {hasPermission("inventory.view") && <StockAlertsCard />}
    </Stack>
  );
}
