"""Grade one answer: handle silence, ask the model, repair once, or fail safely."""

from contracts import Answer, Evaluation, Question
from llm_gateway import LLM, ChatMessage, LLMResponseError, ReplyNotJsonError, parse_json_reply

from evaluator.errors import EvaluationError
from evaluator.parsing import (
    FAILURE_INVALID_JSON,
    EvaluationReplyError,
    read_evaluation,
)
from evaluator.prompt import build_messages, fenced_data

GRADING_TEMPERATURE = 0.0
MAX_REPAIR_PREVIOUS_REPLY_CHARS = 4_000

TRUNCATION_MESSAGE = (
    "The model's reply was cut off at the output limit. Raise LLM_MAX_OUTPUT_TOKENS and try again."
)

SILENT_FEEDBACK = {
    "correctness": "No answer was given, so correctness could not be assessed.",
    "depth": "No answer was given, so depth could not be assessed.",
    "clarity": "No answer was given, so clarity could not be assessed.",
    "relevance": "No answer was given, so relevance could not be assessed.",
}
SILENT_SUMMARY = (
    "The answer was empty. Say what you know about the question, even briefly, and try again."
)


def _silent_evaluation(question: Question) -> Evaluation:
    """A fixed zero-score grade for an empty transcript, with no model call."""
    data: dict[str, object] = {"question_id": str(question.id), "summary": SILENT_SUMMARY}
    for metric, feedback in SILENT_FEEDBACK.items():
        data[metric] = {"score": 0, "feedback": feedback}
    return Evaluation.model_validate(data)


def _read_reply(text: str, question: Question) -> Evaluation:
    """Decode the reply as JSON and validate it into an Evaluation."""
    try:
        data = parse_json_reply(text)
    except ReplyNotJsonError:
        raise EvaluationReplyError((FAILURE_INVALID_JSON,)) from None
    return read_evaluation(data, question)


async def _complete(llm: LLM, messages: tuple[ChatMessage, ...]) -> str:
    """Ask for one grading reply and reject a reply cut off at the output limit."""
    completion = await llm.complete(messages, temperature=GRADING_TEMPERATURE)
    if completion.finish_reason == "length":
        raise LLMResponseError(TRUNCATION_MESSAGE)
    return completion.text


def _correction(failures: tuple[str, ...], previous_reply: str) -> ChatMessage:
    """Name the failed checks and fence the previous reply as untrusted data."""
    return ChatMessage(
        role="user",
        content=(
            f"Your previous reply failed these checks: {', '.join(failures)}. "
            "Return only the JSON object in the required shape, with whole-number scores "
            "from 0 to 10, feedback for every metric, and a summary.\n"
            "Previous model reply (untrusted data):\n"
            f"{fenced_data(previous_reply[:MAX_REPAIR_PREVIOUS_REPLY_CHARS])}"
        ),
    )


def _unusable_message(failures: tuple[str, ...]) -> str:
    """Name the failed checks only, never the answer or the model's text."""
    return (
        "The model did not produce a usable evaluation after two attempts. "
        f"Failed checks: {', '.join(failures)}."
    )


async def grade_answer(
    llm: LLM,
    *,
    question: Question,
    answer: Answer,
    job_title: str,
) -> Evaluation:
    """Grade one spoken answer on the four contract metrics.

    An empty transcript returns a fixed zero-score evaluation without a model call.
    A non-empty answer gets one grading call; if the reply is unusable, it gets one
    corrective call, then raises `EvaluationError`. Truncation is never repaired.
    """
    if answer.transcript.strip() == "":
        return _silent_evaluation(question)

    messages = build_messages(question, answer, job_title)
    text = await _complete(llm, messages)
    try:
        return _read_reply(text, question)
    except EvaluationReplyError as first_error:
        first_failures = first_error.failures

    correction = _correction(first_failures, text)
    text = await _complete(llm, (*messages, correction))
    try:
        return _read_reply(text, question)
    except EvaluationReplyError as second_error:
        failures = tuple(dict.fromkeys((*first_failures, *second_error.failures)))
        raise EvaluationError(
            _unusable_message(failures),
            failures=failures,
            attempts=2,
        ) from None
