"""Build the messages that ask the model for one spoken question."""

from collections.abc import Sequence

from contracts import Preparation, Question, SkillNode
from llm_gateway import ChatMessage

ENGINE_MAX_SPOKEN_QUESTION_LENGTH = 300
MAX_REPAIR_PREVIOUS_REPLY_CHARS = 4_000

FAILURE_REASONS = {
    "empty": "it was empty",
    "too_long": "it was longer than 300 characters",
    "repeat_exact": "it repeated an earlier question",
    "repeat_overlap": "it repeated an earlier question in different words",
    "markdown": "it contained markdown, a heading, a list, a link, or a code block",
    "multiple_questions": "it contained more than one question",
    "not_a_question": "it was not a question",
}


def _fenced_data(value: str) -> str:
    """Wrap untrusted text in a fence longer than any backtick run it contains."""
    longest_run = 0
    current_run = 0
    for character in value:
        if character == "`":
            current_run += 1
            longest_run = max(longest_run, current_run)
        else:
            current_run = 0
    fence = "`" * max(3, longest_run + 1)
    return f"{fence}text\n{value}\n{fence}"


def _system_message() -> ChatMessage:
    """The standing rules for a question that is spoken aloud and shown on screen."""
    return ChatMessage(
        role="system",
        content=(
            "You write one interview question for a spoken mock interview. Ask a single "
            "question only. Use plain sentences: no markdown, no code, no lists, and no "
            f"links. Keep it under {ENGINE_MAX_SPOKEN_QUESTION_LENGTH} characters. Do not "
            "repeat or rephrase earlier questions. The question must stand alone and be "
            "answerable aloud in a couple of minutes. Write only the question, with no "
            "preamble, numbering, or answer."
        ),
    )


def build_messages(
    preparation: Preparation,
    skill: SkillNode,
    difficulty: int,
    earlier_questions: Sequence[Question],
) -> tuple[ChatMessage, ChatMessage]:
    """Build the system and user messages for the next question.

    The job description, the resume, and earlier questions are fenced as data: they
    may contain instructions, and the model must treat them as text.
    """
    system_message = _system_message()
    earlier_text = (
        _fenced_data("\n".join(question.text for question in earlier_questions))
        if earlier_questions
        else "None yet."
    )
    parts = [
        "Job title (untrusted data):",
        _fenced_data(preparation.job_title),
        "",
        "Job description (untrusted data):",
        _fenced_data(preparation.job_description),
    ]
    if preparation.resume is not None:
        parts.extend(["", "Resume (untrusted data):", _fenced_data(preparation.resume)])
    parts.extend(
        [
            "",
            "Skill to ask about (untrusted data):",
            _fenced_data(skill.label),
            f"Difficulty (1 to 5): {difficulty}",
            "",
            "Earlier questions (untrusted data; do not repeat or rephrase them):",
            earlier_text,
        ]
    )
    user_message = ChatMessage(role="user", content="\n".join(parts))
    return system_message, user_message


def build_correction(
    failure: str,
    offending_question: str | None = None,
    *,
    previous_reply: str | None = None,
) -> ChatMessage:
    """Build a plain-language correction with the failed reply fenced as data."""
    reason = FAILURE_REASONS.get(failure, "it did not follow the rules")
    parts = [f"Your previous reply failed because {reason}."]
    if offending_question is not None:
        parts.extend(
            [
                "It repeated this earlier question:",
                _fenced_data(offending_question),
            ]
        )
    if previous_reply is not None:
        parts.extend(
            [
                "Previous reply (untrusted data):",
                _fenced_data(previous_reply[:MAX_REPAIR_PREVIOUS_REPLY_CHARS]),
            ]
        )
    parts.append("Write a different question about the same skill that follows every rule.")
    return ChatMessage(role="user", content="\n".join(parts))
