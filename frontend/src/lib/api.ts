import type { AlertItem, FileItem } from "@/types";

// Base URL for the backend API. Overridable at build time via
// NEXT_PUBLIC_API_URL; defaults to the local dev backend.
const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${url}`, init);
  if (!response.ok) {
    throw new Error("Не удалось выполнить запрос");
  }
  return response.json() as Promise<T>;
}

export function getFiles(): Promise<FileItem[]> {
  return request<FileItem[]>("/files", { cache: "no-store" });
}

export function getAlerts(): Promise<AlertItem[]> {
  return request<AlertItem[]>("/alerts", { cache: "no-store" });
}

export function getDownloadUrl(fileId: string): string {
  return `${API_BASE}/files/${fileId}/download`;
}

export async function uploadFile(title: string, file: File): Promise<FileItem> {
  const formData = new FormData();
  formData.append("title", title);
  formData.append("file", file);

  const response = await fetch(`${API_BASE}/files`, {
    method: "POST",
    body: formData,
  });
  if (!response.ok) {
    throw new Error("Не удалось загрузить файл");
  }
  return response.json() as Promise<FileItem>;
}
