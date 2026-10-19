import { ApiError, createNetworkError, errorFromResponse } from "./errors";
import type { Identity } from "./types";

const IDENTITY_STORAGE_PREFIX = "mockina.identity:";

/** Resolves the configured API origin; an empty value means the current origin. */
export function getApiBaseUrl(): string {
  return (import.meta.env.VITE_API_BASE_URL ?? "").replace(/\/$/, "");
}

/** Returns the storage key scoped to the API instance. */
export function getIdentityStorageKey(): string {
  return `${IDENTITY_STORAGE_PREFIX}${getApiBaseUrl() || window.location.origin}`;
}

/** Reads this browser's anonymous identity for the configured API instance. */
export function getStoredIdentity(): Identity | null {
  try {
    const stored = localStorage.getItem(getIdentityStorageKey());
    if (!stored) return null;
    const identity: unknown = JSON.parse(stored);
    if (!isIdentity(identity)) {
      clearStoredIdentity();
      return null;
    }
    return identity;
  } catch {
    return null;
  }
}

/** Persists the identity returned by the API for this API instance only. */
export function storeIdentity(identity: Identity): void {
  localStorage.setItem(getIdentityStorageKey(), JSON.stringify(identity));
}

/** Removes the current API instance's identity from browser storage. */
export function clearStoredIdentity(): void {
  localStorage.removeItem(getIdentityStorageKey());
}

/** Sends an API request and centralizes auth, JSON, and error-envelope handling. */
export async function request<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body !== undefined && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const token = requiresAuthentication(path, init.method)
    ? getStoredIdentity()?.token
    : null;
  if (token && !headers.has("Authorization"))
    headers.set("Authorization", `Bearer ${token}`);

  let response: Response;
  try {
    response = await fetch(`${getApiBaseUrl()}${path}`, { ...init, headers });
  } catch {
    throw createNetworkError();
  }

  if (response.status === 401) clearStoredIdentity();
  if (!response.ok) throw await errorFromResponse(response);
  if (response.status === 204) return undefined as T;

  try {
    return (await response.json()) as T;
  } catch {
    throw new ApiError("http_error", response.status, false, {}, null);
  }
}

/** Fetches an authenticated streaming response, used for grading SSE. */
export async function requestStream(path: string): Promise<Response> {
  const headers = new Headers({ Accept: "text/event-stream" });
  const token = getStoredIdentity()?.token;
  if (token) headers.set("Authorization", `Bearer ${token}`);

  let response: Response;
  try {
    response = await fetch(`${getApiBaseUrl()}${path}`, { headers });
  } catch {
    throw createNetworkError();
  }

  if (response.status === 401) clearStoredIdentity();
  if (!response.ok) throw await errorFromResponse(response);
  return response;
}

function isIdentity(value: unknown): value is Identity {
  if (typeof value !== "object" || value === null) return false;
  const identity = value as Partial<Identity>;
  return (
    typeof identity.user_id === "string" &&
    typeof identity.token === "string" &&
    typeof identity.created_at === "string"
  );
}

function requiresAuthentication(path: string, method = "GET"): boolean {
  if (path === "/health" || path === "/v1/capabilities") return false;
  if (path === "/v1/identity") return method.toUpperCase() !== "POST";
  if (path === "/v1/job-presets" || path.startsWith("/v1/job-presets/"))
    return false;
  return path.startsWith("/v1/");
}
