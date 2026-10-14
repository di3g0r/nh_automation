import { api } from "./client";
import type { OrderSequence, OrderType, Setting } from "./types";

export const settingsApi = {
  list: () => api.get<Setting[]>("/settings"),
  update: (key: string, value: unknown) => api.patch<Setting>(`/settings/${key}`, { value }),
};

export const sequencesApi = {
  list: () => api.get<OrderSequence[]>("/order-sequences"),
  update: (orderType: OrderType, nextNumber: number) =>
    api.patch<OrderSequence>(`/order-sequences/${orderType}`, { next_number: nextNumber }),
};
