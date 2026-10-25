# session_store

Persistence for the anonymous users, their preparations, and their interview
sessions with every turn, answer and evaluation.

The API and the grading worker depend on the `SessionStore` protocol. Two
implementations satisfy it:

- `SQLiteSessionStore` for real data, behind one dedicated thread;
- `InMemorySessionStore` for tests and local developer routes.

The store knows nothing about HTTP. It raises its own errors and lets the API map
them to status codes.

## What it promises

- **Ownership everywhere.** Every operation is scoped by `user_id`; another user's
  preparation or session behaves exactly like a missing one.
- **Atomic turn changes.** Adding a question, answering, grading and regrading are
  small operations, never a whole-session read-modify-write.
- **One open question.** A partial unique index in SQLite and a check in the in-memory
  store both enforce at most one `awaiting_answer` turn per session.
- **Durability.** SQLite keeps its data across restarts; the in-memory store is for
  tests and dev.
- **Delete means delete.** Deleting a user cascades to preparations, sessions, turns,
  answers and evaluations; SQLite uses `secure_delete` and truncates the WAL so the
  text does not remain in the files.
- **Deterministic tests.** Time is injected; no test waits for a real clock.

## Quick start

```python
from contracts import PreparationCreate
from session_store import SQLiteSessionStore

store = SQLiteSessionStore("data/session-store.sqlite3")
user = await store.create_user(token_hash)
preparation = await store.create_preparation(
    user.id,
    PreparationCreate(
        job_title="Junior React Developer",
        job_description="Build interfaces with React and TypeScript.",
    ),
)
session = await store.create_session(user.id, preparation.id)
```

Use `InMemorySessionStore(clock=...)` in tests. `SessionStoreSettings` reads
`SESSION_STORE_PATH`; the default is `data/session-store.sqlite3`, which is
git-ignored. Set `SESSION_STORE_PATH` to an absolute path when the working directory
is not the repository root.

## Operations

**Users:** create with a token hash, find by token hash, touch last seen at most once
per UTC day, delete with everything, purge inactive users.

**Preparations:** create, get, list newest first with `session_count` and
`last_session_at`, update only while no session exists (and clear the skill graph),
delete with its sessions. The skill graph is stored as JSON on the preparation and
read back through `SkillGraph`.

**Sessions:** create empty and in progress, get with all turns, list newest first with
`turns_total` and `turns_graded`, complete (dropping an unanswered last question),
abandon.

**Turns:** add a question, record an answer idempotently, record an evaluation, record
a grading failure, reset a failed grade, list every awaiting-grade turn across users.
Answers and evaluations are stored as validated contract JSON.

**For the engine:** every question asked in every session of a preparation, in order.

## SQLite details

- One dedicated `ThreadPoolExecutor(max_workers=1)` owns one connection; no operation
  uses a different thread, so `sqlite3`'s thread rule is respected and writes are
  serialized.
- Every write transaction starts with `BEGIN IMMEDIATE`.
- Every connection sets `foreign_keys=ON`, `journal_mode=WAL`, `busy_timeout=5000`
  and `secure_delete=ON`.
- `PRAGMA user_version` tracks the schema version; migrations are ordered functions,
  with no migration library in v1.
- Deleting a user runs `PRAGMA wal_checkpoint(TRUNCATE)` after the transaction.
- A partial unique index (`status = 'awaiting_answer'`) backs up the one-open-question
  rule.

## Errors

| Error | Meaning |
| --- | --- |
| `NotFoundError` | Missing, or owned by somebody else. |
| `PreparationLockedError` | The preparation has a session and can no longer be edited. |
| `InvalidStateError` | The session or turn is not in the state the operation needs. |
| `SessionFullError` | The 100-turn cap is reached. |
| `OpenQuestionError` | The session already has an open question; carries that `Turn`. |

None of these messages contain a token, job text, resume, answer or evaluation.

## Development

From the repo root:

```
uv run pytest packages/session_store
```

The shared suite runs against both implementations; `test_sqlite.py` adds durability
and secure-deletion checks.
