import { useQueryClient } from "@tanstack/react-query";
import { useCallback } from "react";

/** Everything a production change can affect, refreshed after each action. */
export function useInvalidateProduction() {
  const queryClient = useQueryClient();
  return useCallback(() => {
    for (const key of ["orders", "production", "machines-board", "machine-queue", "inventory"]) {
      queryClient.invalidateQueries({ queryKey: [key] });
    }
  }, [queryClient]);
}
