/** Typed fetch wrapper for the ShopSathi backend (`/api/v1`). All pages use this. */

import { clearToken, getToken } from "@/lib/auth/storage";

const BASE_URL = (process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000").replace(/\/$/, "");
const API_PREFIX = "/api/v1";

export class ApiError extends Error {
  constructor(
    public status: number,
    public detail: unknown,
  ) {
    super(formatDetail(detail, status));
    this.name = "ApiError";
  }
}

/** Backend errors are `{"detail": ...}`: a string, or a list of validation errors. */
function formatDetail(detail: unknown, status: number): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    const msgs = detail.map((d) => {
      if (d && typeof d === "object" && "msg" in d) {
        const item = d as { msg: string; loc?: unknown[] };
        const field = item.loc?.filter((p) => typeof p === "string" && p !== "body").pop();
        const msg = item.msg.replace(/^Value error, /, "");
        return field ? `${String(field).replace(/_/g, " ")}: ${msg}` : msg;
      }
      return String(d);
    });
    if (msgs.length) return msgs.join("\n");
  }
  return `Request failed (${status})`;
}

export async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  if (init.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);

  let res: Response;
  try {
    res = await fetch(`${BASE_URL}${API_PREFIX}${path}`, { ...init, headers });
  } catch {
    throw new ApiError(0, "Cannot reach the server");
  }

  const body: unknown = await res.json().catch(() => null);
  if (!res.ok) {
    // An expired/revoked token: drop it and send the user to the login page.
    if (res.status === 401 && token) {
      clearToken();
      if (typeof window !== "undefined" && window.location.pathname !== "/login") {
        // eslint-disable-next-line @next/next/no-location-assign-relative-destination -- full reload resets auth state outside React
        window.location.href = "/login";
      }
    }
    const detail = body && typeof body === "object" && "detail" in body ? (body as { detail: unknown }).detail : null;
    throw new ApiError(res.status, detail);
  }
  return body as T;
}

export const apiPost = <T>(path: string, data?: unknown) =>
  apiFetch<T>(path, { method: "POST", body: data === undefined ? undefined : JSON.stringify(data) });

export interface HealthStatus {
  status: string;
  api: string;
  database: string;
  redis: string;
}

export const getHealth = () => apiFetch<HealthStatus>("/health");
