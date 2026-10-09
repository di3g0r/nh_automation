import { useQuery } from "@tanstack/react-query";

import { inventoryApi } from "../../api/inventory";
import { useAuth } from "../../context/AuthContext";

/** FR-INV-10/11 alerts, shared by the top bar badge and the Inicio card. */
export function useStockAlerts() {
  const { hasPermission } = useAuth();
  return useQuery({
    queryKey: ["inventory-alerts"],
    queryFn: inventoryApi.alerts,
    enabled: hasPermission("inventory.view"),
    refetchInterval: 60_000,
  });
}
