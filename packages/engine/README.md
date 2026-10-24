# engine

The part that decides what the interview does next.

Given a preparation, its skill graph, the session's turns, the questions asked in
earlier sessions, a resolved `InterviewConfig`, and an `LLM`, it returns either a new
`Question` or an `InterviewFinished` that says why the interview is over.

Code decides whether to continue, which skill to ask about, and the difficulty. The
model writes only the question text, as plain prose. The engine stores nothing, never
touches a `Turn`, and grades nothing. It reads no answer text or grade; the end rules
count answered turns and add up their durations.

## What it promises

- **A question or a reason, never a tuple.** The result is `Question | InterviewFinished`.
  "Finished" is a normal return value, not an exception.
- **No model call when code already knows the answer.** A reached question count, a used
  answering time, or a model-decides maximum all return early without asking the model.
- **One question, ready to speak.** Text is trimmed, kept under 300 characters, checked
  for markup, extra questions, and repeats. One corrective retry is allowed; a second
  failure raises `UnusableQuestionError`.
- **Variety without monotony.** Skills are spread across sessions, the same skill is not
  asked twice in a row while another exists, and difficulty starts one below the skill's
  expected level and rises during the session.
- **Gateway errors pass through.** The API already maps every `LLMError`; the engine never
  catches, wraps, or replaces one.

## Quick start

```python
from engine import InterviewFinished, next_turn

outcome = await next_turn(
    preparation,
    skill_graph,
    session.turns,
    earlier_questions,  # from earlier sessions of the same preparation
    interview_config,
    llm,
)
if isinstance(outcome, InterviewFinished):
    print(outcome.reason)  # question_count_reached, answer_time_reached, model_decided
else:
    print(outcome.text, outcome.skill_id, outcome.difficulty)
```

`llm` is any `llm_gateway.LLM`. Tests pass a `FakeLLM`; production passes the same
retrying client the rest of the app uses. Time, randomness, and the model are injected,
so the flow has no hidden state.

## Settings

Instance defaults apply when no user, preparation, or session sets an end rule. They are
environment variables, read once at startup; a bad value stops the app and names the
variable.

| Variable                             | Default | Meaning                                                  |
| ------------------------------------ | ------- | -------------------------------------------------------- |
| `ENGINE_DEFAULT_QUESTION_COUNT`      | `5`     | Questions in a fixed-count interview, 1 to 100.          |
| `ENGINE_DEFAULT_ANSWER_TIME_SECONDS` | `900`   | Total answering time for the time rule, 60 to 3600.      |
| `ENGINE_DEFAULT_MODEL_DECIDES_MIN`   | `3`     | Smallest interview before the model may finish, 1 to 10. |
| `ENGINE_DEFAULT_MODEL_DECIDES_MAX`   | `12`    | Largest interview before code forces a finish, 2 to 20.  |

The minimum must stay below the maximum. The hard limits themselves live in
`contracts.interview_config`, so every layer validates against the same numbers. The
default rule is `QuestionCountConfig(count=ENGINE_DEFAULT_QUESTION_COUNT)`.

## Errors

| Error                   | Meaning                                                               | Retryable |
| ----------------------- | --------------------------------------------------------------------- | --------- |
| `UnusableQuestionError` | The model did not write a usable question after one corrective retry. | yes       |
| `EmptySkillGraphError`  | The graph has no leaf skills to ask about.                            | no        |
| Every `LLMError`        | Passed through unchanged from the gateway.                            | per error |

`UnusableQuestionError` carries `failures` (the failed check names) and `attempts` (2).
Its message names checks only, never the question, prompt, job description, or resume.
`EmptySkillGraphError` is a `ValueError`; it is defensive, because a valid `SkillGraph`
always has at least three leaves.

A reply cut off at the output limit is not retried: it raises `LLMResponseError` with a
message pointing at `LLM_MAX_OUTPUT_TOKENS`.

## Limits

- Questions: 1 to 100 per interview (`MAX_TURNS_PER_SESSION`).
- Spoken question length: 300 characters, stricter than the contract's 1,000.
- Answer-time rule: 60 to 3,600 seconds of summed answering time.
- Model-decides rule: minimum 1 to 10, maximum 2 to 20, minimum strictly below maximum.
- Difficulty: a whole number from 1 to 5.
- Repeats: exact match after normalization across every earlier question, plus
  same-skill word overlap at `REPEAT_THRESHOLD = 0.6`.
- Retry budget: one corrective write, at temperature 0.2.

## Testing code that uses the engine

```python
from engine import QuestionCountConfig, next_turn
from llm_gateway.testing import FakeLLM


async def test_the_engine_asks_a_question_until_the_count_is_reached():
    """A fixed count of one asks once, then reports why it stopped."""
    fake = FakeLLM("How does React batch state updates?")
    question = await next_turn(preparation, graph, [], [], QuestionCountConfig(count=1), fake)
    assert isinstance(question, Question)
```

`FakeLLM` records every call, so a test can assert that the forced end paths made no
model call, and that the decision call happens only inside the model-decides range.

## What it does not do

- **No storage.** The caller supplies turns and earlier questions; the engine writes
  nothing and is safe for a resumed session.
- **No route.** `POST /v1/sessions/{id}/turns` is a later chat's job; the engine is its
  caller.
- **No follow-ups and no grade-aware selection.** It ignores answer text and grades so
  those can be added later without changing `next_turn`'s signature.
- **No config layering.** Resolving instance, user, preparation, and session settings is
  a later chat; the engine takes the resolved config whole.
- **No per-answer timer and no buzzer mode.** Those belong to the client and the answer
  route, not here.

## Development

From the repo root:

```
uv run pytest packages/engine
```
