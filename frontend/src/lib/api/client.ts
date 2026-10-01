/** Typed fetch wrapper for the ShopSathi backend (`/api/v1`). All pages use this. */

const BASE_URL = (process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000").replace(/\/$/, "");
const API_PREFIX = "/api/v1";

export class ApiError extends Error {
  constructor(
    public status: number,
    public detail: unknown,
  ) {
    super(typeof detail === "string" ? detail : `Request failed (${status})`);
    this.name = "ApiError";
  }
}

export async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  if (init.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");

  let res: Response;
  try {
    res = await fetch(`${BASE_URL}${API_PREFIX}${path}`, { ...init, headers });
  } catch {
    throw new ApiError(0, "Cannot reach the server");
  }

  const body: unknown = await res.json().catch(() => null);
  if (!res.ok) {
    const detail = body && typeof body === "object" && "detail" in body ? (body as { detail: unknown }).detail : null;
    throw new ApiError(res.status, detail);
  }
  return body as T;
}

export interface HealthStatus {
  status: string;
  api: string;
  database: string;
  redis: string;
}

export const getHealth = () => apiFetch<HealthStatus>("/health");
