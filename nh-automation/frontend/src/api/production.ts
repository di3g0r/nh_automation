import { api } from "./client";
import type {
  Assignment,
  ChecklistItem,
  MachineBoardItem,
  MachineQueue,
  Order,
  ProductionOrder,
} from "./types";

export interface SplitRow {
  machine_id: number;
  planned_liters: string;
}

/** Phase 3: Producción, expiry, assignments, production controls, traceability, closing. */
export const productionApi = {
  toAssign: () => api.get<ProductionOrder[]>("/production/to-assign"),
  inProduction: () => api.get<ProductionOrder[]>("/production/in-production"),
  toClose: () => api.get<ProductionOrder[]>("/production/to-close"),

  setExpiry: (orderId: number, expiry_date: string | null) =>
    api.put<Order>(`/orders/${orderId}/expiry`, { expiry_date }),
  setAssignments: (orderId: number, assignments: SplitRow[]) =>
    api.put<Order>(`/orders/${orderId}/assignments`, { assignments }),
  reorder: (assignmentId: number, queue_position: number) =>
    api.patch<Assignment>(`/assignments/${assignmentId}/queue-position`, { queue_position }),

  start: (id: number) => api.post<Assignment>(`/assignments/${id}/start`),
  pause: (id: number) => api.post<Assignment>(`/assignments/${id}/pause`),
  resume: (id: number) => api.post<Assignment>(`/assignments/${id}/resume`),
  complete: (id: number, actual_liters: string) =>
    api.post<Assignment>(`/assignments/${id}/complete`, { actual_liters }),

  checklist: (orderId: number, items: { item: ChecklistItem; checked: boolean }[]) =>
    api.patch<Order>(`/orders/${orderId}/checklist`, { items }),
  traceability: (
    orderId: number,
    payload: { new_lot?: string | null; previous_lot?: string | null },
  ) => api.patch<Order>(`/orders/${orderId}/traceability`, payload),
  materials: (
    orderId: number,
    payload: {
      packaging?: { packaging_item_id: number; actual_qty: number | null }[];
      labels_actual?: number | null;
    },
  ) => api.patch<Order>(`/orders/${orderId}/materials`, payload),
  close: (orderId: number, note: string | null) =>
    api.post<Order>(`/orders/${orderId}/close`, { note }),

  board: () => api.get<MachineBoardItem[]>("/machines/board"),
  queue: (machineId: number) => api.get<MachineQueue>(`/machines/${machineId}/queue`),
};
