import { ApiError, createNetworkError, errorFromResponse } from "./errors";
import type { Identity } from "./types";

const IDENTITY_STORAGE_PREFIX = "mockina.identity:";
const memoryIdentities = new Map<string, Identity>();
const unavailableIdentityStorage = new Set<string>();

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
  const storageKey = getIdentityStorageKey();
  try {
    const stored = localStorage.getItem(storageKey);
    if (!stored)
      return unavailableIdentityStorage.has(storageKey)
        ? (memoryIdentities.get(storageKey) ?? null)
        : null;
    const identity: unknown = JSON.parse(stored);
    if (!isIdentity(identity)) {
      clearStoredIdentity();
      return null;
    }
    memoryIdentities.set(storageKey, identity);
    unavailableIdentityStorage.delete(storageKey);
    return identity;
  } catch {
    unavailableIdentityStorage.add(storageKey);
    return memoryIdentities.get(storageKey) ?? null;
  }
}

/** Persists the identity returned by the API for this API instance only. */
export function storeIdentity(identity: Identity): void {
  const storageKey = getIdentityStorageKey();
  memoryIdentities.set(storageKey, identity);
  try {
    localStorage.setItem(storageKey, JSON.stringify(identity));
    unavailableIdentityStorage.delete(storageKey);
  } catch {
    unavailableIdentityStorage.add(storageKey);
  }
}

/** Removes the current API instance's identity from browser storage. */
export function clearStoredIdentity(expectedToken?: string): void {
  const storageKey = getIdentityStorageKey();
  if (expectedToken && getStoredIdentity()?.token !== expectedToken) return;
  memoryIdentities.delete(storageKey);
  try {
    localStorage.removeItem(storageKey);
    unavailableIdentityStorage.delete(storageKey);
  } catch {
    unavailableIdentityStorage.add(storageKey);
  }
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
  const authorization = headers.get("Authorization");
  const sentToken = authorization?.match(/^Bearer\s+(.+)$/i)?.[1] ?? null;

  let response: Response;
  try {
    response = await fetch(`${getApiBaseUrl()}${path}`, { ...init, headers });
  } catch (error) {
    if (isAbortError(error)) throw error;
    throw createNetworkError();
  }

  if (response.status === 401 && sentToken) clearStoredIdentity(sentToken);
  if (!response.ok) throw await errorFromResponse(response);
  if (response.status === 204) return undefined as T;

  try {
    const body = await response.text();
    if (!body.trim()) return undefined as T;
    return JSON.parse(body) as T;
  } catch (error) {
    if (isAbortError(error)) throw error;
    throw new ApiError("http_error", response.status, false, {}, null);
  }
}

/** Fetches an authenticated streaming response, used for grading SSE. */
export async function requestStream(
  path: string,
  signal?: AbortSignal,
): Promise<Response> {
  const headers = new Headers({ Accept: "text/event-stream" });
  const token = getStoredIdentity()?.token;
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const sentToken = token ?? null;

  let response: Response;
  try {
    response = await fetch(`${getApiBaseUrl()}${path}`, { headers, signal });
  } catch (error) {
    if (isAbortError(error)) throw error;
    throw createNetworkError();
  }

  if (response.status === 401 && sentToken) clearStoredIdentity(sentToken);
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
  const pathname = new URL(path, getApiBaseUrl() || "http://localhost")
    .pathname;
  if (pathname === "/health" || pathname === "/v1/capabilities") return false;
  if (pathname === "/v1/identity") return method.toUpperCase() !== "POST";
  if (pathname === "/v1/job-presets" || pathname.startsWith("/v1/job-presets/"))
    return false;
  return pathname.startsWith("/v1/");
}

function isAbortError(error: unknown): error is Error {
  return (
    typeof error === "object" &&
    error !== null &&
    "name" in error &&
    error.name === "AbortError"
  );
}
