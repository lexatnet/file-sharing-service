import type { AlertLevel, ProcessingStatus } from "@/types";

export function formatDate(value: string): string {
  return new Intl.DateTimeFormat("ru-RU", {
    dateStyle: "short",
    timeStyle: "short",
  }).format(new Date(value));
}

export function formatSize(size: number): string {
  if (size < 1024) {
    return `${size} B`;
  }

  if (size < 1024 * 1024) {
    return `${(size / 1024).toFixed(1)} KB`;
  }

  return `${(size / (1024 * 1024)).toFixed(1)} MB`;
}

const LEVEL_VARIANTS: Record<AlertLevel, string> = {
  critical: "danger",
  warning: "warning",
  info: "success",
};

export function getLevelVariant(level: AlertLevel): string {
  return LEVEL_VARIANTS[level];
}

const PROCESSING_VARIANTS: Record<ProcessingStatus, string> = {
  failed: "danger",
  processing: "warning",
  processed: "success",
  uploaded: "secondary",
};

export function getProcessingVariant(status: ProcessingStatus): string {
  return PROCESSING_VARIANTS[status] ?? "secondary";
}
