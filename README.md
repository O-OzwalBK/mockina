# Mockina

An open-source AI mock-interview platform. Pick or paste a job description (and
optionally add your resume), practise with a voice-based AI interviewer, and get
graded feedback on the things a human interviewer would judge. A dashboard shows
which skills are strong and which need work, across all your practice sessions.

> **Status:** early development, built for Frogtoberfest 2026. The shared data
> models are done; the interview engine, grading, voice, and clients are in progress.

## How it will work

1. **Prepare:** choose a target job or paste a job description, and optionally add a resume.
2. **Practise:** an AI interviewer asks questions by voice and you answer out loud.
3. **Get graded:** each answer is scored on correctness, depth, clarity, and
   relevance, with written feedback and delivery measures such as speaking pace and pauses.
4. **See progress:** skills are tracked across all your preparations, so repeated
   practice builds on what you already know instead of starting over.

## Design goals

- **Private by default.** Speech-to-text and text-to-speech run on your own device
  whenever it can handle them, with a cloud fallback for low-end devices.
- **Bring your own model.** The language model is reached through any
  OpenAI-compatible endpoint, whether a hosted provider or a model on your own machine.
- **Documented by construction.** Every data shape carries its own description,
  examples, and limits, and reference documentation is generated from them.

## Repository layout

| Path | Purpose |
|---|---|
| `apps/api` | FastAPI backend |
| `packages/contracts` | Shared data models and their validation rules |
| `packages/engine` | Interview flow (planned) |
| `packages/evaluator` | Grading answers (planned) |
| `packages/llm_gateway` | Talking to language-model providers (planned) |
| `packages/session_store` | Saving and loading sessions (planned) |
| `packages/skill_graph` | Skill identities and mastery tracking (planned) |
| `packages/voice` | Speech-to-text and text-to-speech integration (planned) |
| `docs/schemas` | Generated JSON schemas of the data models |

## Getting started

You need [uv](https://docs.astral.sh/uv/) installed.

```
uv sync --all-packages
uv run pytest
```

Run the API in development mode:

```
cd apps/api
uv run fastapi dev src/api/main.py
```

Then open http://127.0.0.1:8000/docs.

## Documentation

The JSON schemas in `docs/schemas` are generated from the models. After changing
a model, regenerate them:

```
uv run --all-packages python scripts/export_schemas.py
```

## Licence

MIT. See [LICENSE](LICENSE).