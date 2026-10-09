import { api } from "./client";
import type { ImportKind, ImportMode, ImportResult, ImportSource } from "./types";

function form(source: string, mode: ImportMode, file: File | null): FormData {
  const data = new FormData();
  data.set("source", source);
  data.set("mode", mode);
  if (file) data.set("file", file);
  return data;
}

export const importsApi = {
  sources: (kind: ImportKind) =>
    api.get<{ kind: ImportKind; sources: ImportSource[] }>(`/imports/${kind}/sources`),
  preview: (kind: ImportKind, source: string, mode: ImportMode, file: File | null) =>
    api.postForm<ImportResult>(`/imports/${kind}/preview`, form(source, mode, file)),
  confirm: (kind: ImportKind, source: string, mode: ImportMode, file: File | null) =>
    api.postForm<ImportResult>(`/imports/${kind}/confirm`, form(source, mode, file)),
};
