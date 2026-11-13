# API

The FastAPI application exposes the backend over JSON.

Run it from the repository root after
`uv sync --all-packages`:

```powershell
cd apps/api
uv run fastapi dev src/api/main.py
```

Open `http://127.0.0.1:8000/docs` for the generated OpenAPI reference. `/health` does not call the
model. Developer model tools are registered only when `API_DEV_ROUTES=true`; keep that setting
false in deployed copies.

## Developer routes

`POST /v1/dev/extract-skills` accepts a job title and description and returns a validated skill
graph with `elapsed_ms`. It deliberately has no resume field: skill extraction is based on the job.
The request uses the same title and description limits as `PreparationCreate` and rejects unknown
fields. The endpoint uses the app's configured `LLM` and in-memory catalog; tests can replace both
through FastAPI dependency overrides.

`POST /v1/dev/extract-skills/raw?job_title=...` takes the job description as a `text/plain` body,
so a description pasted from a job board needs no JSON escaping at all. It applies the same limits
and returns the same response as the JSON route.

`POST /v1/dev/grade` grades one answer with the supplied question and job title and returns the
evaluation, elapsed time, and provider token counts. It stores nothing.

`POST /v1/dev/complete` sends a supplied conversation to the model, and `GET /v1/dev/model` reports
non-secret configuration details. These are also developer-only routes.

## Interview questions

`POST /v1/sessions/{session_id}/turns` asks the next question of a session. It is safe to repeat:
while a question is waiting for its answer, the same question comes back with status 200 and the
model is not asked again; otherwise a new question is stored and the answer is 201.

The skills a preparation is asked about are extracted **lazily**. Nothing is extracted when the
preparation is created. The first question of a preparation reads the job description, asks the
model for a skill graph, and saves it on the preparation. Every later question, in any session of
that preparation, reuses the saved graph. Creating the first session locks the job text, so the
graph is always built from the final text, and a preparation that is never practised never costs a
model call. If writing the question fails after the extraction, the graph is kept, so the retry
does not pay for it again.

Two requests that need the same work do not do it twice: a lock per session stops two questions
being asked at once, and a lock per preparation stops two extractions. These locks live in the
memory of one process, so run the API as a single process (`--workers 1`).

A question that takes longer than `API_TURN_TIMEOUT_SECONDS` (default 90) answers 504
`llm_timeout`, which is retryable. `409 session_finished` means the interview has no more
questions (`details.reason` says why); `409 invalid_state` means the session is completed or
abandoned.

**Interview length.** How the interview ends is decided once, when the server starts, by
`resolve_interview_config`: today it is `ENGINE_DEFAULT_QUESTION_COUNT` questions (5 by default).
The value is not stored with the session. If you change `ENGINE_DEFAULT_QUESTION_COUNT` and restart
the server, a session that is already running ends by the new number. Per-session snapshots of
the end rule will remove this until they land.

## Errors and privacy

Failures use the shared `{"error": {"code", "message", "retryable", "details"}}` envelope. The
`code` is stable for client handling. Logs contain model outcome and usage metadata, never prompts,
job descriptions, model reply text, or keys. Model failures map through the existing gateway error
codes; an unusable skill graph maps to `llm_bad_response`.

## Development

```powershell
uv run pytest apps/api
```
