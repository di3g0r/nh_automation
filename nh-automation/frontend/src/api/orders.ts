import { api } from "./client";
import { toQuery } from "./types";
import type {
  Order,
  OrderComment,
  OrderHistoryEntry,
  OrderListItem,
  OrderPayload,
  OrderPrintData,
  OrderType,
  Page,
} from "./types";

export interface OrderListParams {
  /** One status or several, comma-separated. */
  status?: string | null;
  order_type?: OrderType | null;
  date_from?: string | null;
  date_to?: string | null;
  client_id?: number | null;
  razon_social_id?: number | null;
  product_id?: number | null;
  site_id?: number | null;
  search?: string;
  page?: number;
  page_size?: number;
}

export const ordersApi = {
  list: (params: OrderListParams) =>
    api.get<Page<OrderListItem>>(`/orders${toQuery({ ...params })}`),
  get: (id: number) => api.get<Order>(`/orders/${id}`),
  create: (payload: OrderPayload) => api.post<Order>("/orders", payload),
  update: (id: number, payload: OrderPayload) => api.patch<Order>(`/orders/${id}`, payload),
  remove: (id: number) => api.del<void>(`/orders/${id}`),
  cancel: (id: number, reason: string) => api.post<Order>(`/orders/${id}/cancel`, { reason }),
  comments: (id: number) => api.get<OrderComment[]>(`/orders/${id}/comments`),
  addComment: (id: number, text: string) =>
    api.post<OrderComment>(`/orders/${id}/comments`, { text }),
  history: (id: number) => api.get<OrderHistoryEntry[]>(`/orders/${id}/history`),
  printData: (id: number) => api.get<OrderPrintData>(`/orders/${id}/print-data`),
};
