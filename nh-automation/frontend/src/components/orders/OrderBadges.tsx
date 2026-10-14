import { Badge } from "@mantine/core";

import type { OrderStatus, OrderType } from "../../api/types";
import { strings } from "../../i18n/strings";
import { STATUS_COLOR } from "../../utils/orders";

export function OrderTypeBadge({ type, size = "md" }: { type: OrderType; size?: string }) {
  return (
    <Badge size={size} variant="filled" color={type === "retrabajo" ? "grape" : "indigo"}>
      {strings.orders.tipos[type]}
    </Badge>
  );
}

export function OrderStatusBadge({ status, size = "md" }: { status: OrderStatus; size?: string }) {
  return (
    <Badge size={size} variant="light" color={STATUS_COLOR[status]}>
      {strings.orders.estados[status]}
    </Badge>
  );
}
