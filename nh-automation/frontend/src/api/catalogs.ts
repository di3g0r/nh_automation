import { api } from "./client";
import { toQuery } from "./types";
import type { Client, Machine, MachineWithKey, PackagingItem, Page, Product, Site } from "./types";

export interface ListParams {
  search?: string;
  active?: boolean;
  page?: number;
  page_size?: number;
  category?: string;
}

/** CRUD for one catalog resource. Deactivation is PATCH {is_active: false}. */
function resource<T, TCreate = Partial<T>, TCreated = T>(path: string) {
  return {
    list: (params: ListParams = {}) => api.get<Page<T>>(`${path}${toQuery({ ...params })}`),
    get: (id: number) => api.get<T>(`${path}/${id}`),
    create: (payload: TCreate) => api.post<TCreated>(path, payload),
    update: (id: number, payload: Partial<T>) => api.patch<T>(`${path}/${id}`, payload),
  };
}

export const productsApi = resource<Product>("/products");
export const packagingApi = resource<PackagingItem>("/packaging-items");
export const clientsApi = resource<Client>("/clients");
export const sitesApi = resource<Site>("/sites");
export const machinesApi = {
  ...resource<Machine, Partial<Machine>, MachineWithKey>("/machines"),
  rotateKey: (id: number) => api.post<MachineWithKey>(`/machines/${id}/rotate-key`),
};
