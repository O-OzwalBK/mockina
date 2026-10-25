import { ApiError, apiRequest } from "./api";

/** What the Dashboard needs to show one preparation. */
export type PreparationSummary = {
  id: string;
  title: string;
  createdAt: string;
  sessionCount: number;
  lastPractisedAt: string | null;
};

/** Assumed shape of GET /v1/preparations. Adjust when the server route exists. */
type ServerPreparation = {
  id: string;
  job_title: string;
  created_at: string;
  session_count: number;
  last_practised_at?: string | null;
};

// Mock data stays on until the server route exists. Set VITE_USE_MOCK=false to use the real API.
const USE_MOCK = import.meta.env.VITE_USE_MOCK !== "false";

const MOCK: PreparationSummary[] = [
  {
    id: "p1",
    title: "Product Designer",
    createdAt: "2026-10-22T09:00:00Z",
    sessionCount: 0,
    lastPractisedAt: null,
  },
  {
    id: "p2",
    title: "Backend Engineer",
    createdAt: "2026-10-20T09:00:00Z",
    sessionCount: 3,
    lastPractisedAt: "2026-10-21T18:30:00Z",
  },
  {
    id: "p3",
    title: "Data Analyst",
    createdAt: "2026-10-18T09:00:00Z",
    sessionCount: 1,
    lastPractisedAt: "2026-10-18T20:05:00Z",
  },
];

function wait(ms: number, signal?: AbortSignal) {
  return new Promise<void>((resolve, reject) => {
    const timer = setTimeout(resolve, ms);
    signal?.addEventListener("abort", () => {
      clearTimeout(timer);
      reject(new DOMException("Aborted", "AbortError"));
    });
  });
}

/** Open the app with ?mock=empty or ?mock=error to see those states. */
async function mockList(signal?: AbortSignal): Promise<PreparationSummary[]> {
  await wait(500, signal);
  const scenario = new URLSearchParams(window.location.search).get("mock");
  if (scenario === "error")
    throw new ApiError({ code: "network_error", status: 0, retryable: true });
  if (scenario === "empty") return [];
  return MOCK;
}

/** List the person's preparations, newest first. */
export async function getPreparations(
  signal?: AbortSignal,
): Promise<PreparationSummary[]> {
  if (USE_MOCK) return mockList(signal);
  const rows = await apiRequest<ServerPreparation[]>("/v1/preparations", {
    signal,
  });
  return rows.map((row) => ({
    id: row.id,
    title: row.job_title,
    createdAt: row.created_at,
    sessionCount: row.session_count,
    lastPractisedAt: row.last_practised_at ?? null,
  }));
}
