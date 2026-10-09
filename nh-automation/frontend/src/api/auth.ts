import { api } from "./client";
import type { Me, User } from "./types";

export const authApi = {
  login: (username: string, password: string) =>
    api.post<User>("/auth/login", { username, password }),

  pinLogin: (username: string, pin: string) => api.post<User>("/auth/pin-login", { username, pin }),

  logout: () => api.post<{ ok: boolean }>("/auth/logout"),

  me: () => api.get<Me>("/auth/me"),

  changePassword: (payload: {
    current_password: string;
    new_password?: string;
    new_pin?: string;
  }) => api.post<User>("/auth/change-password", payload),
};
