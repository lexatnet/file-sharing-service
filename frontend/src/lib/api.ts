import type { AlertItem, FileItem } from "@/types";

// Base URL for the backend API. Overridable at build time via
// NEXT_PUBLIC_API_URL; defaults to the local dev backend.
const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// Pending (resumable) uploads are remembered in localStorage keyed by the
// file name+size, so an interrupted upload can be continued on the next try
// with the same file — already-uploaded chunks are skipped.
const PENDING_KEY_PREFIX = "pending-upload:v1:";

type UploadInitResponse = {
  file_id: string;
  stored_name: string;
  upload_id: string;
  part_size: number;
  num_parts: number;
};

type UploadInfoResponse = {
  file_id: string;
  upload_id: string;
  part_size: number;
  num_parts: number;
  uploaded_parts: number[];
};

type PresignPartItem = {
  part_number: number;
  presigned_url: string;
};

export type UploadOptions = {
  onProgress?: (percent: number) => void;
  signal?: AbortSignal;
};

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${url}`, init);
  if (!response.ok) {
    const detail = await response.text().catch(() => "");
    throw new Error(detail || "Не удалось выполнить запрос");
  }
  return response.json() as Promise<T>;
}

function pendingKey(file: File): string {
  return `${PENDING_KEY_PREFIX}${file.name}:${file.size}`;
}

function loadPending(file: File): { file_id: string } | null {
  if (typeof window === "undefined") return null;
  const raw = window.localStorage.getItem(pendingKey(file));
  if (!raw) return null;
  try {
    return JSON.parse(raw) as { file_id: string };
  } catch {
    return null;
  }
}

async function initUpload(
  title: string,
  file: File,
): Promise<UploadInitResponse> {
  return request<UploadInitResponse>("/files/uploads", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      title,
      original_name: file.name,
      size: file.size,
      mime_type: file.type || "application/octet-stream",
    }),
  });
}

async function getUploadInfo(fileId: string): Promise<UploadInfoResponse> {
  return request<UploadInfoResponse>(`/files/uploads/${fileId}`, {
    cache: "no-store",
  });
}

async function presignParts(
  fileId: string,
  partNumbers: number[],
): Promise<PresignPartItem[]> {
  return request<PresignPartItem[]>(`/files/uploads/${fileId}/presign`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ part_numbers: partNumbers }),
  });
}

async function completeUpload(fileId: string): Promise<FileItem> {
  return request<FileItem>(`/files/uploads/${fileId}/complete`, {
    method: "POST",
  });
}

async function abortUpload(fileId: string): Promise<void> {
  await fetch(`${API_BASE}/files/uploads/${fileId}`, { method: "DELETE" });
}

/**
 * Stream-slice the file into `partSize` chunks and PUT each not-yet-uploaded
 * chunk to its presigned S3 URL. Fails fast on a bad response; the caller
 * retries later using the parts already persisted in S3.
 */
async function uploadMissingParts(
  file: File,
  fileId: string,
  partSize: number,
  numParts: number,
  uploadedParts: number[],
  options: UploadOptions,
): Promise<void> {
  const uploaded = new Set(uploadedParts);

  for (let n = 1; n <= numParts; n++) {
    if (uploaded.has(n)) {
      continue; // already in S3 — resume skips these
    }
    const start = (n - 1) * partSize;
    const chunk = file.slice(start, start + partSize);
    const [item] = await presignParts(fileId, [n]);
    const response = await fetch(item.presigned_url, {
      method: "PUT",
      body: chunk,
      signal: options.signal,
    });
    if (!response.ok) {
      throw new Error("Не удалось загрузить часть файла");
    }
    options.onProgress?.(Math.round((n / numParts) * 100));
  }
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

/**
 * Chunked, resumable upload: initialize a multipart upload, PUT the chunks to
 * S3, complete it. If a pending upload for the same file (name+size) exists,
 * continue from its already-uploaded chunks instead of restarting.
 */
export async function uploadFile(
  title: string,
  file: File,
  options: UploadOptions = {},
): Promise<FileItem> {
  const resumed = loadPending(file);
  if (resumed) {
    const done = await resumeUpload(title, file, resumed.file_id, options);
    if (done) {
      return done;
    }
    // Resume failed (stale/aborted multipart): drop it and start fresh.
    try {
      await abortUpload(resumed.file_id);
    } catch {
      /* the server may already have cleared it — ignore */
    }
    window.localStorage.removeItem(pendingKey(file));
  }

  const init = await initUpload(title, file);
  if (typeof window !== "undefined") {
    window.localStorage.setItem(
      pendingKey(file),
      JSON.stringify({ file_id: init.file_id }),
    );
  }

  const fileId = init.file_id;
  try {
    await uploadMissingParts(
      file,
      fileId,
      init.part_size,
      init.num_parts,
      [],
      options,
    );
    const item = await completeUpload(fileId);
    if (typeof window !== "undefined") {
      window.localStorage.removeItem(pendingKey(file));
    }
    return item;
  } catch (error) {
    if (options.signal?.aborted) {
      // User cancelled: free the multipart upload server-side.
      try {
        await abortUpload(fileId);
      } catch {
        /* noop */
      }
      if (typeof window !== "undefined") {
        window.localStorage.removeItem(pendingKey(file));
      }
    }
    throw error;
  }
}

async function resumeUpload(
  title: string,
  file: File,
  fileId: string,
  options: UploadOptions,
): Promise<FileItem | null> {
  try {
    const info = await getUploadInfo(fileId);
    await uploadMissingParts(
      file,
      fileId,
      info.part_size,
      info.num_parts,
      info.uploaded_parts,
      options,
    );
    const item = await completeUpload(fileId);
    if (typeof window !== "undefined") {
      window.localStorage.removeItem(pendingKey(file));
    }
    return item;
  } catch (error) {
    if (options.signal?.aborted) {
      throw error; // resume was cancelled — propagate to the caller
    }
    return null; // resume failed; caller starts a fresh upload
  }
}