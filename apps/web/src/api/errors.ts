import type { ApiErrorEnvelope, ValidationIssue } from "./types";

const ERROR_MESSAGES = {
  invalid_request:
    "Some information is invalid. Check the fields and try again.",
  network_error:
    "The server could not be reached. Check your connection and try again.",
  unauthorized:
    "Your local identity has expired. A new identity is required; previous history cannot be recovered.",
  not_found: "This item could not be found. It may have been deleted.",
  preparation_locked:
    "This preparation can no longer be edited. Duplicate it to make changes.",
  invalid_state:
    "This action is no longer available. Refresh the latest session state and try again.",
  session_finished: "There are no more questions in this interview.",
  rate_limited: "Too many requests. Wait a moment before trying again.",
  llm_rate_limited: "The model is busy. Wait a moment, then try again.",
  llm_timeout: "The model took too long to respond. You can try again.",
  llm_unreachable: "The model service could not be reached. You can try again.",
  llm_server_error:
    "The model service encountered an error. You can try again.",
  llm_bad_response:
    "The model service returned an invalid response. You can try again.",
  llm_auth_failed:
    "The model service is misconfigured. Contact the instance administrator.",
  llm_rejected_request:
    "The model service could not process this request. Contact the instance administrator.",
  context_too_large: "This request is too large for the configured model.",
  internal_error: "Something went wrong on the server. Try again later.",
  model_not_configured: "The model is not configured on this server.",
  method_not_allowed: "This action is not supported by the server.",
  http_error: "The server could not complete this request.",
} as const;

export type ApiErrorCode = keyof typeof ERROR_MESSAGES;

/** A safe, structured error for API failures; server messages are never shown to users. */
export class ApiError extends Error {
  readonly code: ApiErrorCode;
  readonly status: number;
  readonly retryable: boolean;
  readonly details: Record<string, unknown>;
  readonly retryAfterSeconds: number | null;

  constructor(
    code: ApiErrorCode,
    status: number,
    retryable: boolean,
    details: Record<string, unknown>,
    retryAfterSeconds: number | null,
  ) {
    super(ERROR_MESSAGES[code]);
    this.name = "ApiError";
    this.code = code;
    this.status = status;
    this.retryable = retryable;
    this.details = details;
    this.retryAfterSeconds = retryAfterSeconds;
  }

  get validationIssues(): ValidationIssue[] {
    const errors = this.details.errors;
    if (!Array.isArray(errors)) return [];
    return errors.filter(isValidationIssue);
  }
}

/** Returns a user-safe network error for failures that have no HTTP response. */
export function createNetworkError(): ApiError {
  return new ApiError("network_error", 0, true, {}, null);
}

/** Converts an HTTP response into the shared typed error without exposing its message. */
export async function errorFromResponse(response: Response): Promise<ApiError> {
  let envelope: ApiErrorEnvelope | undefined;
  try {
    envelope = (await response.json()) as ApiErrorEnvelope;
  } catch (error) {
    if (isAbortError(error)) throw error;
    envelope = undefined;
  }

  const error = envelope?.error;
  const retryAfter = response.headers.get("Retry-After");
  const retryAfterSeconds = parseRetryAfter(retryAfter);

  return new ApiError(
    isApiErrorCode(error?.code) ? error.code : "http_error",
    response.status,
    typeof error?.retryable === "boolean"
      ? error.retryable
      : response.status >= 500,
    isRecord(error?.details) ? error.details : {},
    retryAfterSeconds,
  );
}

function isAbortError(error: unknown): error is Error {
  return (
    typeof error === "object" &&
    error !== null &&
    "name" in error &&
    error.name === "AbortError"
  );
}

export function isApiErrorCode(value: unknown): value is ApiErrorCode {
  return typeof value === "string" && Object.hasOwn(ERROR_MESSAGES, value);
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function parseRetryAfter(value: string | null): number | null {
  if (!value) return null;
  const seconds = Number(value);
  if (Number.isFinite(seconds)) return Math.max(0, seconds);
  const timestamp = Date.parse(value);
  return Number.isNaN(timestamp)
    ? null
    : Math.max(0, (timestamp - Date.now()) / 1000);
}

function isValidationIssue(value: unknown): value is ValidationIssue {
  if (!isRecord(value)) return false;
  return (
    Array.isArray(value.loc) &&
    value.loc.every(
      (part) => typeof part === "string" || typeof part === "number",
    ) &&
    typeof value.msg === "string" &&
    typeof value.type === "string"
  );
}
