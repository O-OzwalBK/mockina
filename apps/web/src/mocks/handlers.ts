import { http, HttpResponse } from "msw";
import type { Capabilities, Identity, JobPreset, Preparation, PreparationSummary } from "../api";

const capabilities: Capabilities = {
  anonymous_retention_days: 30,
  hosted_stt: false,
  dev_routes: true,
  limits: {
    max_job_title_length: 120,
    max_job_description_length: 20000,
    max_resume_length: 20000,
    max_transcript_length: 20000,
    max_words_per_answer: 5000,
    max_word_length: 100,
    max_answer_seconds: 600,
  },
};

const presets: JobPreset[] = [
  {
    id: "junior-react-developer",
    job_title: "Junior React Developer",
    category: "frontend",
    job_description: "Build accessible interfaces with React and TypeScript.",
  },
  {
    id: "backend-python-engineer",
    job_title: "Backend Python Engineer",
    category: "backend",
    job_description: "Build and operate APIs with Python and PostgreSQL.",
  },
];

const preparations: Preparation[] = [];

function summarize(prep: Preparation): PreparationSummary {
  return {
    id: prep.id,
    job_title: prep.job_title,
    created_at: prep.created_at,
    session_count: 0,
    last_session_at: null,
  };
}

function notFound() {
  return HttpResponse.json(
    { error: { code: "not_found", message: "Not Found", retryable: false, details: {} } },
    { status: 404 },
  );
}

/** Handlers for server routes that are not built yet. */
export const handlers = [
  http.get("/v1/capabilities", () => HttpResponse.json(capabilities)),
  http.post("/v1/identity", () => {
    const identity: Identity = {
      user_id: crypto.randomUUID(),
      token: crypto.randomUUID() + crypto.randomUUID(),
      created_at: new Date().toISOString(),
    };
    return HttpResponse.json(identity, { status: 201 });
  }),
  http.delete("/v1/identity", () => new HttpResponse(null, { status: 204 })),
  http.get("/v1/job-presets", ({ request }) => {
    const url = new URL(request.url);
    const q = url.searchParams.get("q")?.toLowerCase();
    const category = url.searchParams.get("category");
    const items = presets
      .filter((p) => !category || p.category === category)
      .filter((p) => !q || p.job_title.toLowerCase().includes(q))
      .map(({ id, job_title, category }) => ({ id, job_title, category }));
    return HttpResponse.json({ items });
  }),
  http.get("/v1/job-presets/:id", ({ params }) => {
    const preset = presets.find((p) => p.id === params.id);
    return preset ? HttpResponse.json(preset) : notFound();
  }),
  http.get("/v1/preparations", () =>
    HttpResponse.json({ items: preparations.map(summarize).reverse() }),
  ),
  http.post("/v1/preparations", async ({ request }) => {
    const body = (await request.json()) as {
      job_title: string;
      job_description: string;
      resume?: string | null;
    };
    const prep: Preparation = {
      id: crypto.randomUUID(),
      created_at: new Date().toISOString(),
      job_title: body.job_title,
      job_description: body.job_description,
      resume: body.resume ?? null,
    };
    preparations.push(prep);
    return HttpResponse.json(prep, { status: 201 });
  }),
  http.get("/v1/preparations/:id", ({ params }) => {
    const prep = preparations.find((p) => p.id === params.id);
    return prep ? HttpResponse.json(prep) : notFound();
  }),
  http.delete("/v1/preparations/:id", ({ params }) => {
    const index = preparations.findIndex((p) => p.id === params.id);
    if (index === -1) return notFound();
    preparations.splice(index, 1);
    return new HttpResponse(null, { status: 204 });
  }),
];
