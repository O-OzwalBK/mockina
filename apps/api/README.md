# API

The FastAPI application exposes the backend over JSON. Run it from the repository root after
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

`POST /v1/dev/complete` sends a supplied conversation to the model, and `GET /v1/dev/model` reports
non-secret configuration details. These are also developer-only routes.

## Errors and privacy

Failures use the shared `{"error": {"code", "message", "retryable", "details"}}` envelope. The
`code` is stable for client handling. Logs contain model outcome and usage metadata, never prompts,
job descriptions, model reply text, or keys. Model failures map through the existing gateway error
codes; an unusable skill graph maps to `llm_bad_response`.

## Development

```powershell
uv run pytest apps/api
```
