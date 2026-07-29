const configuredApiBase = (process.env.NEXT_PUBLIC_CORTEX_API_BASE || "").trim().replace(/\/$/, "");

export function apiUrl(path: string): string {
  if (/^https?:\/\//i.test(path)) return path;
  if (configuredApiBase) return `${configuredApiBase}${path}`;
  if (typeof window !== "undefined" && window.location.port === "3420") {
    return `http://127.0.0.1:8420${path}`;
  }
  return path;
}

export class ApiError extends Error {
  status: number;
  detail: unknown;

  constructor(status: number, message: string, detail?: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  if (init?.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  const response = await fetch(apiUrl(path), { ...init, headers, cache: "no-store" });
  const contentType = response.headers.get("content-type") || "";
  const body = contentType.includes("application/json")
    ? await response.json()
    : await response.text();
  if (!response.ok) {
    const message =
      typeof body === "object" && body && "detail" in body
        ? String((body as { detail: unknown }).detail)
        : typeof body === "object" && body && "message" in body
          ? String((body as { message: unknown }).message)
          : `Request failed (${response.status})`;
    throw new ApiError(response.status, message, body);
  }
  return body as T;
}

export function postJson<T>(path: string, body: unknown, init?: RequestInit): Promise<T> {
  return api<T>(path, { ...init, method: "POST", body: JSON.stringify(body) });
}

export function putJson<T>(path: string, body: unknown): Promise<T> {
  return api<T>(path, { method: "PUT", body: JSON.stringify(body) });
}

export function formatDuration(ms?: number | null): string {
  if (ms == null || !Number.isFinite(ms)) return "—";
  if (ms < 1000) return `${Math.round(ms)} ms`;
  if (ms < 60_000) return `${(ms / 1000).toFixed(ms < 10_000 ? 1 : 0)} s`;
  const minutes = Math.floor(ms / 60_000);
  const seconds = Math.round((ms % 60_000) / 1000);
  return `${minutes}m ${seconds}s`;
}

export function formatBytes(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes <= 0) return "—";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let value = bytes;
  let index = 0;
  while (value >= 1024 && index < units.length - 1) {
    value /= 1024;
    index += 1;
  }
  return `${value.toFixed(index > 2 ? 1 : 0)} ${units[index]}`;
}

export function shortTime(value?: string | number | null): string {
  if (!value) return "";
  const date = typeof value === "number" ? new Date(value * 1000) : new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  const today = new Date();
  if (date.toDateString() === today.toDateString()) {
    return new Intl.DateTimeFormat("fr-FR", { hour: "2-digit", minute: "2-digit" }).format(date);
  }
  return new Intl.DateTimeFormat("fr-FR", { month: "short", day: "numeric" }).format(date);
}

export function relativeEta(elapsedMs: number, estimateMs?: number | null): string {
  if (!estimateMs || estimateMs <= elapsedMs) return "estimation…";
  const remaining = estimateMs - elapsedMs;
  const low = Math.max(1, Math.round((remaining * 0.7) / 1000));
  const high = Math.max(low + 1, Math.round((remaining * 1.3) / 1000));
  return `env. ${low}–${high}s`;
}
