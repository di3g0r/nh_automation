import { api } from "./client";
import type { Setting } from "./types";

export const settingsApi = {
  list: () => api.get<Setting[]>("/settings"),
  update: (key: string, value: unknown) => api.patch<Setting>(`/settings/${key}`, { value }),
};
