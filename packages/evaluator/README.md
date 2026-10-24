# evaluator

Grades one spoken interview answer on the four shared metrics.

Given a `Question`, the candidate's `Answer`, a job title, and an `LLM`, it returns a
`contracts.Evaluation` with correctness, depth, clarity, relevance, and a summary. It
stores nothing, never touches a `Turn`, and never chooses a model.

## What it promises

- **Four metrics, one contract.** The result is the shared `Evaluation`; the server
  supplies `question_id` from the question, never the model.
- **No silence in the model.** An empty transcript returns a fixed zero-score
  evaluation with clear feedback and makes no model call.
- **One repair, then a named failure.** An unusable reply gets one corrective call;
  after that the evaluator raises `EvaluationError` instead of returning a guess.
- **No clamped scores.** Out-of-range scores are model mistakes to repair, not values
  to squeeze into 0-10.
- **Gateway errors pass through.** A timeout, a bad key, or an oversized prompt is
  not disguised as a bad grade.
- **Nothing private in errors.** Messages never contain the answer, the prompt, or the
  job title.

## Quick start

```python
from contracts import Answer, Question
from evaluator import grade_answer
from llm_gateway import LLM


async def grade(llm: LLM, question: Question, answer: Answer) -> None:
    evaluation = await grade_answer(
        llm,
        question=question,
        answer=answer,
        job_title="Junior React Developer",
    )
    print(evaluation.correctness.score, evaluation.summary)
```

`llm` is any `llm_gateway.LLM`. Tests pass a `FakeLLM`; production passes the same
retrying client the rest of the app uses.

## Inputs and output

| In | Meaning |
| --- | --- |
| `question` | The question text and its difficulty. The id is copied into the result. |
| `answer` | The spoken answer. Only `transcript` is graded; word timings and duration are delivery data. |
| `job_title` | Short role context. The job description is deliberately **not** sent. |

| Out | Meaning |
| --- | --- |
| `Evaluation` | Four `MetricScore` values and one summary. |

## Scoring

- Scores are whole numbers from 0 to 10. Fractions are rounded to the nearest whole
  number, half up, for v1.
- `"7"`, `"7/10"`, and `"7 out of 10"` are accepted. Out-of-range, non-numeric, and
  boolean scores are rejected and repaired; they are never clamped.
- Every metric needs nonblank feedback, and the result needs a summary.
- Difficulty is context only. A 10 means a complete, correct answer for this question
  at its stated difficulty; the scale is absolute, so grades stay comparable.
- The transcript may contain speech-to-text artifacts. The rubric says not to penalize
  missing punctuation, filler words, mis-heard words, or occasional Nepali words.

## Errors

| Error | Meaning | Retryable |
| --- | --- | --- |
| `EvaluationError` | The model did not produce a usable evaluation after one repair. | no |
| `LLMResponseError` | A truncated reply; the fix is `LLM_MAX_OUTPUT_TOKENS`, not another prompt. | no |
| Every other `LLMError` | Passed through unchanged from the gateway. | per error |

`EvaluationError` carries `failures` (safe check names) and `attempts` (2). It is
deliberately not retryable: grading runs in the background, and a failed grade is
retried through the product's regrade path. The API maps it to `502 llm_bad_response`.

## Limits

- One grading call, plus at most one corrective call: two model calls total.
- Grade temperature is 0.0 for consistency.
- Feedback at most 1,000 characters; summary at most 2,000 (contract limits).
- The job title is sent, never the job description.
- Repair prompts keep at most 4,000 characters of the previous reply.

## Testing code that uses the evaluator

```python
import json

from evaluator import grade_answer
from llm_gateway.testing import FakeLLM

reply = {
    "correctness": {"score": 7, "feedback": "Right idea."},
    "depth": {"score": 6, "feedback": "Could go further."},
    "clarity": {"score": 8, "feedback": "Clear."},
    "relevance": {"score": 7, "feedback": "On topic."},
    "summary": "Add one concrete example.",
}
fake = FakeLLM(json.dumps(reply))
evaluation = await grade_answer(
    fake, question=question, answer=answer, job_title="Frontend Engineer"
)
```

`FakeLLM` records every call, so a test can assert that silence made no call, that
grading used temperature 0, and that a repair sent the previous reply fenced.

## What it does not do

- **No storage.** It returns an `Evaluation`; the grading worker stores it.
- **No queue or worker.** Moving a `Turn` to graded or `grading_failed` is the
  grading worker's job.
- **No delivery stats.** Pace, pauses, and filler words are computed by the web client
  from word timings.
- **No config resolution, no route, no model choice.** Those belong to other parts.
- **No JSON mode.** It reads the free-text reply through `llm_gateway.parse_json_reply`.

## Development

From the repo root:

```
uv run pytest packages/evaluator
```
