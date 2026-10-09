import { api } from "./client";
import type { Page, Role, User } from "./types";

export const usersApi = {
  list: (search?: string) =>
    api.get<Page<User>>(`/users${search ? `?search=${encodeURIComponent(search)}` : ""}`),

  create: (payload: {
    username: string;
    full_name: string;
    role: Role;
    password: string;
    pin?: string;
  }) => api.post<User>("/users", payload),

  update: (id: number, payload: { full_name?: string; role?: Role }) =>
    api.patch<User>(`/users/${id}`, payload),

  deactivate: (id: number) => api.post<User>(`/users/${id}/deactivate`),

  activate: (id: number) => api.post<User>(`/users/${id}/activate`),

  resetCredentials: (id: number, payload: { password?: string; pin?: string }) =>
    api.post<User>(`/users/${id}/reset-credentials`, payload),
};
