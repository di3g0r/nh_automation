import { api } from "./client";
import { toQuery } from "./types";
import type {
  Alerts,
  Availability,
  InventoryRow,
  ItemType,
  Movement,
  MovementType,
  MovementUser,
  Page,
} from "./types";

export interface InventoryParams {
  item_type: ItemType;
  site_id?: number | null;
  category?: string | null;
  search?: string;
  low_stock?: boolean;
  negative?: boolean;
  include_inactive?: boolean;
  page?: number;
  page_size?: number;
}

export interface MovementParams {
  item_type?: ItemType | null;
  item_id?: number | null;
  site_id?: number | null;
  type?: MovementType | null;
  user_id?: number | null;
  date_from?: string | null;
  date_to?: string | null;
  page?: number;
  page_size?: number;
}

export const inventoryApi = {
  list: (params: InventoryParams) =>
    api.get<Page<InventoryRow>>(`/inventory${toQuery({ ...params })}`),
  movements: (params: MovementParams) =>
    api.get<Page<Movement>>(`/inventory/movements${toQuery({ ...params })}`),
  movementUsers: () => api.get<MovementUser[]>("/inventory/movement-users"),
  availability: (item_type: ItemType, item_id: number, site_id: number) =>
    api.get<Availability>(`/inventory/availability${toQuery({ item_type, item_id, site_id })}`),
  alerts: () => api.get<Alerts>("/inventory/alerts"),
  receipt: (payload: {
    item_type: ItemType;
    item_id: number;
    site_id: number;
    quantity: string;
    note?: string;
  }) => api.post<Movement>("/inventory/receipts", payload),
  adjustment: (payload: {
    item_type: ItemType;
    item_id: number;
    site_id: number;
    counted_quantity: string;
    reason: string;
  }) => api.post<Movement>("/inventory/adjustments", payload),
};
