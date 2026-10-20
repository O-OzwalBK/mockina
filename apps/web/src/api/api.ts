import { clearStoredIdentity, request, requestStream } from "./client";
import type {
  Answer,
  AnswerReceipt,
  Capabilities,
  CompletionRequest,
  CompletionResponse,
  DevModelInfo,
  GradingStatus,
  Identity,
  InterviewSession,
  JobPreset,
  JobPresetSummary,
  Preparation,
  PreparationCreate,
  PreparationSummary,
  Progress,
  SessionSummary,
  Turn,
} from "./types";

const jsonBody = (body: unknown): string => JSON.stringify(body);
const encode = (value: string): string => encodeURIComponent(value);

/** Reads server capabilities and live request limits. */
export const getCapabilities = (): Promise<Capabilities> =>
  request("/v1/capabilities");

/** Creates a new anonymous identity. */
export const createIdentity = (): Promise<Identity> =>
  request("/v1/identity", { method: "POST" });

/** Deletes the current identity and every record owned by it. */
export async function deleteIdentity(): Promise<void> {
  await request<void>("/v1/identity", { method: "DELETE" });
  clearStoredIdentity();
}

/** Lists available job presets, optionally filtered by search and category. */
export function getJobPresets(
  filters: { q?: string; category?: string } = {},
): Promise<{ items: JobPresetSummary[] }> {
  const query = new URLSearchParams();
  if (filters.q) query.set("q", filters.q);
  if (filters.category) query.set("category", filters.category);
  const suffix = query.size > 0 ? `?${query.toString()}` : "";
  return request(`/v1/job-presets${suffix}`);
}

/** Reads one preset by its stable slug identifier. */
export const getJobPreset = (presetId: string): Promise<JobPreset> =>
  request(`/v1/job-presets/${encode(presetId)}`);

/** Creates a preparation from validated job and optional resume text. */
export const createPreparation = (
  input: PreparationCreate,
): Promise<Preparation> =>
  request("/v1/preparations", { method: "POST", body: jsonBody(input) });

/** Lists the current identity's preparations, newest first. */
export const getPreparations = (): Promise<{ items: PreparationSummary[] }> =>
  request("/v1/preparations");

/** Reads one preparation. */
export const getPreparation = (preparationId: string): Promise<Preparation> =>
  request(`/v1/preparations/${encode(preparationId)}`);

/** Updates a preparation before it has any sessions. */
export const updatePreparation = (
  preparationId: string,
  changes: Partial<PreparationCreate>,
): Promise<Preparation> =>
  request(`/v1/preparations/${encode(preparationId)}`, {
    method: "PATCH",
    body: jsonBody(changes),
  });

/** Deletes a preparation and its sessions. */
export const deletePreparation = (preparationId: string): Promise<void> =>
  request(`/v1/preparations/${encode(preparationId)}`, { method: "DELETE" });

/** Starts a session without asking its first question. */
export const createSession = (
  preparationId: string,
): Promise<InterviewSession> =>
  request(`/v1/preparations/${encode(preparationId)}/sessions`, {
    method: "POST",
  });

/** Lists sessions belonging to one preparation. */
export const getPreparationSessions = (
  preparationId: string,
): Promise<{ items: SessionSummary[] }> =>
  request(`/v1/preparations/${encode(preparationId)}/sessions`);

/** Reads a session and all of its turns. */
export const getSession = (
  sessionId: string,
): Promise<InterviewSession> =>
  request(`/v1/sessions/${encode(sessionId)}`);

/** Requests the next question, or the existing open question when one exists. */
export const getNextTurn = (sessionId: string): Promise<Turn> =>
  request(`/v1/sessions/${encode(sessionId)}/turns`, { method: "POST" });

/** Submits an answer for the named question. */
export const submitAnswer = (
  sessionId: string,
  questionId: string,
  answer: Answer,
): Promise<AnswerReceipt> =>
  request(
    `/v1/sessions/${encode(sessionId)}/turns/${encode(questionId)}/answer`,
    {
      method: "PUT",
      body: jsonBody(answer),
    },
  );

/** Retries grading for one failed turn. */
export const regradeTurn = (
  sessionId: string,
  questionId: string,
): Promise<Turn> =>
  request(
    `/v1/sessions/${encode(sessionId)}/turns/${encode(questionId)}/regrade`,
    {
      method: "POST",
    },
  );

/** Completes an interview session. */
export const completeSession = (sessionId: string): Promise<SessionSummary> =>
  request(`/v1/sessions/${encode(sessionId)}/complete`, { method: "POST" });

/** Abandons an interview session without marking it completed. */
export const abandonSession = (sessionId: string): Promise<SessionSummary> =>
  request(`/v1/sessions/${encode(sessionId)}/abandon`, { method: "POST" });

/** Opens the authenticated grading event stream. */
export const getSessionEvents = (
  sessionId: string,
  signal?: AbortSignal,
): Promise<Response> =>
  requestStream(`/v1/sessions/${encode(sessionId)}/events`, signal);

/** Reads grading statuses without loading answer transcripts or timings. */
export const getSessionStatus = (sessionId: string): Promise<GradingStatus> =>
  request(`/v1/sessions/${encode(sessionId)}/status`);

/** Loads progress for all preparations or one selected preparation. */
export function getProgress(preparationId?: string): Promise<Progress> {
  const query = preparationId ? `?preparation_id=${encode(preparationId)}` : "";
  return request(`/v1/progress${query}`);
}

/** Reads non-secret configuration for the development model endpoint. */
export const getDevModel = (): Promise<DevModelInfo> =>
  request("/v1/dev/model");

/** Sends a development prompt to the configured model. */
export const completeDevPrompt = (
  input: CompletionRequest,
): Promise<CompletionResponse> =>
  request("/v1/dev/complete", { method: "POST", body: jsonBody(input) });

/** Checks API liveness without requiring identity or capabilities routes. */
export const getHealth = (): Promise<{ status: string }> => request("/health");
