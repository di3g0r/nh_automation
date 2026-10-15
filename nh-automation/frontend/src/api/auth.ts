import { api } from "./client";
import type { Me, User } from "./types";

export const authApi = {
  login: (username: string, password: string) =>
    api.post<User>("/auth/login", { username, password }),

  logout: () => api.post<{ ok: boolean }>("/auth/logout"),

  me: () => api.get<Me>("/auth/me"),

  changePassword: (payload: { current_password: string; new_password: string }) =>
    api.post<User>("/auth/change-password", payload),
};
