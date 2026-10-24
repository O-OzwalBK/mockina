"""Check a written question and repair it once when it cannot be spoken aloud."""

from collections.abc import Sequence
from dataclasses import dataclass

from contracts import Question
from llm_gateway import LLM, ChatMessage, LLMResponseError

from engine.errors import UnusableQuestionError
from engine.prompt import ENGINE_MAX_SPOKEN_QUESTION_LENGTH, build_correction
from engine.repeat import find_repeat

QUESTION_TEMPERATURE = 0.7
RETRY_TEMPERATURE = 0.2
QUESTION_MAX_OUTPUT_TOKENS: int | None = None

TRUNCATION_MESSAGE = (
    "The model's reply was cut off at the output limit. Raise LLM_MAX_OUTPUT_TOKENS and try again."
)

FAILURE_EMPTY = "empty"
FAILURE_TOO_LONG = "too_long"
FAILURE_REPEAT_EXACT = "repeat_exact"
FAILURE_REPEAT_OVERLAP = "repeat_overlap"
FAILURE_MARKDOWN = "markdown"
FAILURE_MULTIPLE_QUESTIONS = "multiple_questions"
FAILURE_NOT_A_QUESTION = "not_a_question"

MARKDOWN_CHARACTERS = ("\\", "*", "#", "[", "]", "`")
IMPERATIVE_STARTS = (
    "explain",
    "describe",
    "name",
    "walk",
    "tell",
    "discuss",
    "define",
    "list",
    "compare",
    "contrast",
    "outline",
    "summarize",
    "summarise",
    "give",
)


@dataclass(frozen=True)
class CheckResult:
    """The first check a question failed, or no failure at all."""

    failure: str | None = None
    """The failed check's name, or None when the question passed."""

    offending_question: str | None = None
    """The earlier question a repeat copied, used only to write the correction."""


def _has_markdown(text: str) -> bool:
    """True when the text contains markup or a bulleted line, none of which can be spoken."""
    if any(character in text for character in MARKDOWN_CHARACTERS):
        return True
    return any(line.startswith("- ") for line in text.splitlines())


def _question_marks_outside_quotes(text: str) -> int:
    """Count question marks that are not inside a double-quoted phrase."""
    count = 0
    in_quotes = False
    for character in text:
        if character in {'"', "“", "”"}:
            in_quotes = not in_quotes
        elif character == "?" and not in_quotes:
            count += 1
    return count


def _starts_with_imperative(text: str) -> bool:
    """True when the text opens with a verb that makes it a spoken instruction."""
    lowered = text.lstrip().lower()
    return any(lowered.startswith(verb) for verb in IMPERATIVE_STARTS)


def check_question(
    text: str,
    *,
    skill_id: str,
    earlier_questions: Sequence[Question],
) -> CheckResult:
    """Run the check suite in order, returning at the first failure.

    The order matters: a repeated question is reported before its markup, and a
    truncation is handled by the caller before the text is checked at all.
    """
    stripped = text.strip()
    if not stripped:
        return CheckResult(failure=FAILURE_EMPTY)
    if len(stripped) > ENGINE_MAX_SPOKEN_QUESTION_LENGTH:
        return CheckResult(failure=FAILURE_TOO_LONG)

    repeat = find_repeat(stripped, earlier_questions, skill_id=skill_id)
    if repeat is not None:
        return CheckResult(failure=repeat.kind, offending_question=repeat.earlier_question)

    if _has_markdown(stripped):
        return CheckResult(failure=FAILURE_MARKDOWN)
    if _question_marks_outside_quotes(stripped) > 1:
        return CheckResult(failure=FAILURE_MULTIPLE_QUESTIONS)
    if "?" not in stripped and not _starts_with_imperative(stripped):
        return CheckResult(failure=FAILURE_NOT_A_QUESTION)
    return CheckResult()


async def _write_once(
    llm: LLM,
    messages: Sequence[ChatMessage],
    *,
    temperature: float,
) -> str:
    """Ask for one question and reject a reply cut off at the output limit."""
    completion = await llm.complete(
        messages,
        temperature=temperature,
        max_output_tokens=QUESTION_MAX_OUTPUT_TOKENS,
    )
    if completion.finish_reason == "length":
        raise LLMResponseError(TRUNCATION_MESSAGE)
    return completion.text.strip()


def _unusable_message(failures: Sequence[str]) -> str:
    """Name the failed checks only, never the question, prompt, job, or resume."""
    return (
        "The model did not write a usable question after two attempts. "
        f"Failed checks: {', '.join(failures)}."
    )


async def write_question(
    llm: LLM,
    messages: Sequence[ChatMessage],
    *,
    skill_id: str,
    earlier_questions: Sequence[Question],
) -> str:
    """Write one question, retrying once with a correction, then fail as unusable.

    Truncation is never retried: the fix is the output-token setting, not another
    attempt. Every other failure gets exactly one corrective retry at a low
    temperature, and a second failure raises `UnusableQuestionError`.
    """
    text = await _write_once(llm, messages, temperature=QUESTION_TEMPERATURE)
    first_result = check_question(text, skill_id=skill_id, earlier_questions=earlier_questions)
    if first_result.failure is None:
        return text

    correction = build_correction(first_result.failure, first_result.offending_question)
    retry_messages = (*messages, correction)
    text = await _write_once(llm, retry_messages, temperature=RETRY_TEMPERATURE)
    second_result = check_question(text, skill_id=skill_id, earlier_questions=earlier_questions)
    if second_result.failure is None:
        return text

    failures = tuple(
        dict.fromkeys(
            failure
            for failure in (first_result.failure, second_result.failure)
            if failure is not None
        )
    )
    raise UnusableQuestionError(_unusable_message(failures), failures=failures, attempts=2)
