import { Anchor, Badge, Card, Group, Stack, Text, Title } from "@mantine/core";
import { IconAlertTriangle } from "@tabler/icons-react";
import { Link } from "react-router-dom";

import type { AlertItem } from "../../api/types";
import { strings } from "../../i18n/strings";
import { formatQuantity } from "../../utils/quantity";
import { useStockAlerts } from "./useStockAlerts";

const t = strings.alerts;

function AlertLine({ alert }: { alert: AlertItem }) {
  const detail =
    alert.kind === "low_stock"
      ? `${t.disponible} ${formatQuantity(alert.item_type, alert.available)} / ${t.umbral} ${formatQuantity(
          alert.item_type,
          alert.low_stock_threshold ?? 0,
        )}`
      : formatQuantity(alert.item_type, alert.on_hand);
  return (
    <Group justify="space-between" wrap="nowrap">
      <div>
        <Text size="sm" fw={500}>
          {alert.code} — {alert.name}
        </Text>
        <Text size="xs" c="dimmed">
          {alert.site_name}
        </Text>
      </div>
      <Badge color={alert.kind === "low_stock" ? "orange" : "red"} variant="light">
        {detail}
      </Badge>
    </Group>
  );
}

/** Inicio: stock alerts card (FR-INV-10/11). */
export function StockAlertsCard() {
  const { data } = useStockAlerts();
  if (!data) return null;

  return (
    <Card withBorder maw={720}>
      <Group justify="space-between" mb="sm">
        <Group gap="xs">
          <IconAlertTriangle size={20} color={data.count ? "orange" : "gray"} />
          <Title order={4}>{t.title}</Title>
          {data.count > 0 && <Badge color="orange">{data.count}</Badge>}
        </Group>
        <Anchor component={Link} to="/inventario?tab=materiales&alertas=1" size="sm">
          {t.verInventario}
        </Anchor>
      </Group>
      {data.count === 0 && <Text c="dimmed">{t.ninguna}</Text>}
      <Stack gap="xs">
        {data.negative_stock.length > 0 && (
          <Text size="sm" fw={600} c="red">
            {t.negativo}
          </Text>
        )}
        {data.negative_stock.map((a) => (
          <AlertLine key={`n-${a.item_type}-${a.item_id}-${a.site_id}`} alert={a} />
        ))}
        {data.low_stock.length > 0 && (
          <Text size="sm" fw={600} c="orange">
            {t.stockBajo}
          </Text>
        )}
        {data.low_stock.map((a) => (
          <AlertLine key={`l-${a.item_id}-${a.site_id}`} alert={a} />
        ))}
      </Stack>
    </Card>
  );
}
