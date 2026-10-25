import { http, HttpResponse, passthrough } from "msw";
import type {
  Answer,
  Capabilities,
  Identity,
  InterviewSession,
  JobPreset,
  Preparation,
  PreparationSummary,
  Question,
  SessionSummary,
  Turn,
} from "../api";

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
const sessions = new Map<string, InterviewSession>();

const interviewQuestions: Question[] = [
  {
    id: "question-1",
    skill_id: "communication",
    difficulty: 1,
    text: "Tell me about yourself and your professional background.",
  },
  {
    id: "question-2",
    skill_id: "technical-knowledge",
    difficulty: 2,
    text: "What skills and technologies are most relevant to this role?",
  },
  {
    id: "question-3",
    skill_id: "problem-solving",
    difficulty: 3,
    text: "Tell me about a challenging problem you solved. How did you approach it?",
  },
  {
    id: "question-4",
    skill_id: "teamwork",
    difficulty: 3,
    text: "Describe a time you received feedback and used it to improve your work.",
  },
  {
    id: "question-5",
    skill_id: "role-fit",
    difficulty: 3,
    text: "Why are you interested in this role, and what would you bring to the team?",
  },
];

function summarize(prep: Preparation): PreparationSummary {
  const prepSessions = [...sessions.values()].filter(
    (session) => session.preparation_id === prep.id,
  );

  return {
    id: prep.id,
    job_title: prep.job_title,
    created_at: prep.created_at,
    session_count: prepSessions.length,
    last_session_at: prepSessions.length
      ? (prepSessions
          .map((session) => session.started_at)
          .sort()
          .at(-1) ?? null)
      : null,
  };
}

function summarizeSession(session: InterviewSession): SessionSummary {
  return {
    id: session.id,
    preparation_id: session.preparation_id,
    status: session.status,
    started_at: session.started_at,
    ended_at: session.ended_at,
    turns_total: session.turns.length,
    turns_graded: session.turns.filter((turn) => turn.status === "graded")
      .length,
  };
}

function notFound() {
  return HttpResponse.json(
    {
      error: {
        code: "not_found",
        message: "Not Found",
        retryable: false,
        details: {},
      },
    },
    { status: 404 },
  );
}

function sessionNotFound() {
  return HttpResponse.json(
    {
      error: {
        code: "not_found",
        message: "Interview session not found.",
        retryable: false,
        details: {},
      },
    },
    { status: 404 },
  );
}

function invalidSessionState(message: string) {
  return HttpResponse.json(
    {
      error: {
        code: "invalid_state",
        message,
        retryable: false,
        details: {},
      },
    },
    { status: 409 },
  );
}

/** Mock handlers for capabilities, identity, preparations, and interviews. */

const useRealBackend = import.meta.env.VITE_USE_REAL_PREPARATIONS === "true";

export const handlers = [
  // Forward existing backend endpoints to FastAPI.
  ...(useRealBackend
    ? [
        http.post("/v1/identity", () => passthrough()),
        http.delete("/v1/identity", () => passthrough()),
        http.get("/v1/preparations", () => passthrough()),
        http.post("/v1/preparations", () => passthrough()),
        http.get("/v1/preparations/:id", () => passthrough()),
      ]
    : []),

  // Capabilities remain mocked.
  http.get("/v1/capabilities", () => HttpResponse.json(capabilities)),

  // Identity
  http.post("/v1/identity", () => {
    const identity: Identity = {
      user_id: crypto.randomUUID(),
      token: crypto.randomUUID() + crypto.randomUUID(),
      created_at: new Date().toISOString(),
    };

    return HttpResponse.json(identity, { status: 201 });
  }),

  http.delete("/v1/identity", () => new HttpResponse(null, { status: 204 })),

  // Job presets
  http.get("/v1/job-presets", ({ request }) => {
    const url = new URL(request.url);
    const q = url.searchParams.get("q")?.toLowerCase();
    const category = url.searchParams.get("category");

    const items = presets
      .filter((preset) => !category || preset.category === category)
      .filter((preset) => !q || preset.job_title.toLowerCase().includes(q))
      .map(({ id, job_title, category }) => ({ id, job_title, category }));

    return HttpResponse.json({ items });
  }),

  http.get("/v1/job-presets/:id", ({ params }) => {
    const preset = presets.find((item) => item.id === params.id);

    return preset ? HttpResponse.json(preset) : notFound();
  }),

  // Preparations
  http.get("/v1/preparations", () =>
    HttpResponse.json({
      items: preparations.map(summarize).reverse(),
    }),
  ),

  http.post("/v1/preparations", async ({ request }) => {
    const body = (await request.json()) as {
      job_title: string;
      job_description: string;
      resume?: string | null;
    };

    const preparation: Preparation = {
      id: crypto.randomUUID(),
      created_at: new Date().toISOString(),
      job_title: body.job_title,
      job_description: body.job_description,
      resume: body.resume ?? null,
    };

    preparations.push(preparation);

    return HttpResponse.json(preparation, { status: 201 });
  }),

  http.get("/v1/preparations/:id", ({ params }) => {
    const preparation = preparations.find((item) => item.id === params.id);

    return preparation ? HttpResponse.json(preparation) : notFound();
  }),

  http.delete("/v1/preparations/:id", ({ params }) => {
    const index = preparations.findIndex((item) => item.id === params.id);

    if (index === -1) return notFound();

    const preparationId = preparations[index].id;
    preparations.splice(index, 1);

    for (const [sessionId, session] of sessions) {
      if (session.preparation_id === preparationId) {
        sessions.delete(sessionId);
      }
    }

    return new HttpResponse(null, { status: 204 });
  }),

  // Create an interview session
  http.post("/v1/preparations/:id/sessions", ({ params }) => {
    const preparationId = String(params.id);

    const preparation = preparations.find((item) => item.id === preparationId);

    // Real preparations come from the backend, so they won't
    // necessarily exist in MSW's local preparations array.
    if (!preparation && !useRealBackend) {
      return notFound();
    }

    const now = new Date().toISOString();

    const session: InterviewSession = {
      id: crypto.randomUUID(),
      preparation_id: preparationId,
      status: "in_progress",
      started_at: now,
      ended_at: null,
      updated_at: now,
      turns: [],
    };

    sessions.set(session.id, session);

    return HttpResponse.json(session, { status: 201 });
  }),

  // List interview sessions for a preparation
  http.get("/v1/preparations/:id/sessions", ({ params }) => {
    if (!preparations.some((item) => item.id === params.id)) {
      return notFound();
    }

    const items = [...sessions.values()]
      .filter((session) => session.preparation_id === params.id)
      .map(summarizeSession)
      .reverse();

    return HttpResponse.json({ items });
  }),

  // Get an interview session
  http.get("/v1/sessions/:id", ({ params }) => {
    const session = sessions.get(String(params.id));

    return session ? HttpResponse.json(session) : sessionNotFound();
  }),

  // Get the existing unanswered question or create the next question
  http.post("/v1/sessions/:id/turns", ({ params }) => {
    const session = sessions.get(String(params.id));

    if (!session) return sessionNotFound();

    if (session.status !== "in_progress") {
      return invalidSessionState("This interview has already ended.");
    }

    const openTurn = session.turns.find(
      (turn) => turn.status === "awaiting_answer",
    );

    if (openTurn) return HttpResponse.json(openTurn);

    const nextIndex = session.turns.length;

    if (nextIndex >= interviewQuestions.length) {
      return HttpResponse.json(
        {
          error: {
            code: "session_finished",
            message: "There are no more questions in this interview.",
            retryable: false,
            details: {},
          },
        },
        { status: 409 },
      );
    }

    const turn: Turn = {
      question: interviewQuestions[nextIndex],
      answer: null,
      evaluation: null,
      grading_error: null,
      status: "awaiting_answer",
    };

    session.turns.push(turn);
    session.updated_at = new Date().toISOString();

    return HttpResponse.json(turn, { status: 201 });
  }),

  // Submit an answer to a question
  http.put(
    "/v1/sessions/:id/turns/:questionId/answer",
    async ({ params, request }) => {
      const session = sessions.get(String(params.id));

      if (!session) return sessionNotFound();

      if (session.status !== "in_progress") {
        return invalidSessionState("This interview has already ended.");
      }

      const turn = session.turns.find(
        (item) => item.question.id === params.questionId,
      );

      if (!turn) {
        return HttpResponse.json(
          {
            error: {
              code: "not_found",
              message: "Question not found.",
              retryable: false,
              details: {},
            },
          },
          { status: 404 },
        );
      }

      const answer = (await request.json()) as Answer;

      // Repeating the same request is safe.
      if (turn.answer) {
        if (JSON.stringify(turn.answer) === JSON.stringify(answer)) {
          return HttpResponse.json({
            question_id: turn.question.id,
            status: turn.status,
          });
        }

        return invalidSessionState(
          "This question already has a different answer.",
        );
      }

      if (turn.status !== "awaiting_answer") {
        return invalidSessionState("This question is not accepting an answer.");
      }

      turn.answer = answer;
      turn.status = "awaiting_grade";
      session.updated_at = new Date().toISOString();

      return HttpResponse.json({
        question_id: turn.question.id,
        status: "awaiting_grade",
      });
    },
  ),

  // Complete an interview after at least one answer has been submitted
  http.post("/v1/sessions/:id/complete", ({ params }) => {
    const session = sessions.get(String(params.id));

    if (!session) return sessionNotFound();

    const hasAnswer = session.turns.some((turn) => turn.answer !== null);

    if (!hasAnswer) {
      return invalidSessionState(
        "Submit at least one answer before ending the interview.",
      );
    }

    // Drop a question that is still awaiting an answer.
    session.turns = session.turns.filter(
      (turn) => turn.status !== "awaiting_answer",
    );

    session.status = "completed";
    session.ended_at = new Date().toISOString();
    session.updated_at = session.ended_at;

    return HttpResponse.json(summarizeSession(session));
  }),

  // Leave an interview without marking it completed
  http.post("/v1/sessions/:id/abandon", ({ params }) => {
    const session = sessions.get(String(params.id));

    if (!session) return sessionNotFound();

    session.turns = session.turns.filter(
      (turn) => turn.status !== "awaiting_answer",
    );

    session.status = "abandoned";
    session.ended_at = new Date().toISOString();
    session.updated_at = session.ended_at;

    return HttpResponse.json(summarizeSession(session));
  }),
];
