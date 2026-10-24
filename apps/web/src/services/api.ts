const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";

export type ApiErrorCode =
  | "network_error" | "invalid_request" | "not_found" | "method_not_allowed"
  | "http_error" | "internal_error" | "context_too_large" | "llm_rate_limited"
  | "llm_timeout" | "llm_unreachable" | "llm_server_error" | "llm_bad_response"
  | "llm_auth_failed" | "llm_rejected_request" | "model_not_configured";

const SAFE_MESSAGES: Record<ApiErrorCode, string> = {
  network_error: "Can't reach the server. Check your connection and try again.",
  invalid_request: "Some of the information you entered is not valid.",
  not_found: "This item could not be found.",
  method_not_allowed: "Something went wrong. Please reload the page.",
  http_error: "Something went wrong. Please try again.",
  internal_error: "Something went wrong on the server.",
  context_too_large: "That request is too large. Try shortening it.",
  llm_rate_limited: "The AI service is busy. Please wait a moment and try again.",
  llm_timeout: "The AI service took too long. Please try again.",
  llm_unreachable: "The AI service is unreachable right now. Please try again.",
  llm_server_error: "The AI service had a problem. Please try again.",
  llm_bad_response: "The AI service sent an unusable reply. Please try again.",
  llm_auth_failed: "The server is misconfigured. Contact the instance administrator.",
  llm_rejected_request: "The server is misconfigured. Contact the instance administrator.",
  model_not_configured: "No AI model is configured on this server.",
};

export class ApiError extends Error {
  code: ApiErrorCode;
  status: number;
  retryable: boolean;
  retryAfterSeconds?: number;
  details: Record<string, unknown>;

  constructor(init: {
    code: ApiErrorCode;
    status: number;
    retryable: boolean;
    retryAfterSeconds?: number;
    details?: Record<string, unknown>;
  }) {
    super(SAFE_MESSAGES[init.code]);
    this.name = "ApiError";
    this.code = init.code;
    this.status = init.status;
    this.retryable = init.retryable;
    this.retryAfterSeconds = init.retryAfterSeconds;
    this.details = init.details ?? {};
  }
}

const KNOWN_CODES = new Set(Object.keys(SAFE_MESSAGES));

/** Call the API and return parsed JSON, or throw an ApiError with a user-safe message. */
export async function apiRequest<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...init?.headers },
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    throw new ApiError({ code: "network_error", status: 0, retryable: true });
  }

  if (!response.ok) {
    let body: { error?: { code?: string; retryable?: boolean; details?: Record<string, unknown> } } = {};
    try {
      body = await response.json();
    } catch {
      /* non-JSON error body */
    }
    const rawCode = body.error?.code ?? "http_error";
    const code = (KNOWN_CODES.has(rawCode) ? rawCode : "http_error") as ApiErrorCode;
    const retryAfter = Number(response.headers.get("Retry-After"));
    throw new ApiError({
      code,
      status: response.status,
      retryable: body.error?.retryable ?? false,
      retryAfterSeconds: Number.isFinite(retryAfter) && retryAfter > 0 ? retryAfter : undefined,
      details: body.error?.details,
    });
  }
  return response.json() as Promise<T>;
}

export type HealthResponse = { status: string };

export type ModelInfo = {
  model: string;
  host: string;
  context_tokens: number;
  max_output_tokens: number;
  api_key_set: boolean;
};

export type ChatMessage = { role: "system" | "user" | "assistant"; content: string };

export type CompletionResult = {
  text: string;
  model: string;
  finish_reason: string | null;
  prompt_tokens: number | null;
  completion_tokens: number | null;
  elapsed_ms: number;
};

export const getHealth = (signal?: AbortSignal) =>
  apiRequest<HealthResponse>("/health", { signal });

export const getDevModel = (signal?: AbortSignal) =>
  apiRequest<ModelInfo>("/v1/dev/model", { signal });

export const completeDevPrompt = (
  body: { messages: ChatMessage[]; temperature?: number; max_output_tokens?: number },
  signal?: AbortSignal,
) => apiRequest<CompletionResult>("/v1/dev/complete", {
  method: "POST",
  body: JSON.stringify(body),
  signal,
});
