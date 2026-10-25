"""Decide whether the interview is over before the engine asks another question."""

import re
from collections.abc import Sequence

from contracts import (
    AnswerTimeConfig,
    InterviewConfig,
    ModelDecidesConfig,
    QuestionCountConfig,
    Turn,
)
from contracts.session import MAX_TURNS_PER_SESSION
from llm_gateway import LLM, ChatMessage

from engine.results import FinishedReason, InterviewFinished

DECISION_TEMPERATURE = 0.0
DECISION_MAX_OUTPUT_TOKENS = 64


def _total_answer_seconds(turns: Sequence[Turn]) -> float:
    """The summed duration of every answered turn; an open turn adds nothing."""
    return sum(turn.answer.duration for turn in turns if turn.answer is not None)


def _decision_messages(
    questions_asked: int, config: ModelDecidesConfig
) -> tuple[ChatMessage, ChatMessage]:
    """Ask for exactly one word, with the position and range stated to prevent drift."""
    system_message = ChatMessage(
        role="system",
        content=(
            "You decide whether a mock interview should continue. Reply with exactly one "
            "word: continue or finish. Do not explain."
        ),
    )
    user_message = ChatMessage(
        role="user",
        content=(
            f"Questions asked so far: {questions_asked}\n"
            f"Minimum before you may finish: {config.min_questions}\n"
            f"Maximum allowed: {config.max_questions}\n"
            "Reply continue or finish."
        ),
    )
    return system_message, user_message


async def _model_decides(
    config: ModelDecidesConfig, questions_asked: int, llm: LLM
) -> InterviewFinished | None:
    """Apply the boundaries, then consult the model only inside the open range."""
    if questions_asked < config.min_questions:
        return None
    if questions_asked >= config.max_questions:
        return InterviewFinished(reason=FinishedReason.QUESTION_COUNT_REACHED)

    completion = await llm.complete(
        _decision_messages(questions_asked, config),
        temperature=DECISION_TEMPERATURE,
        max_output_tokens=DECISION_MAX_OUTPUT_TOKENS,
    )
    words = re.findall(r"[a-z]+", completion.text.lower())
    decisions = [word for word in words if word in {"continue", "finish"}]
    if decisions and decisions[-1] == "finish":
        return InterviewFinished(reason=FinishedReason.MODEL_DECIDED)
    return None


async def is_finished(
    config: InterviewConfig,
    turns: Sequence[Turn],
    llm: LLM,
) -> InterviewFinished | None:
    """Return the finish result when the configured rule says to stop, or None to continue.

    A count or time rule is pure code and never calls the model. A model-decides
    rule calls the model only when the question count is inside its open range.
    """
    if len(turns) >= MAX_TURNS_PER_SESSION:
        return InterviewFinished(reason=FinishedReason.QUESTION_COUNT_REACHED)
    if isinstance(config, QuestionCountConfig):
        if len(turns) >= config.count:
            return InterviewFinished(reason=FinishedReason.QUESTION_COUNT_REACHED)
        return None
    if isinstance(config, AnswerTimeConfig):
        if _total_answer_seconds(turns) >= config.max_seconds:
            return InterviewFinished(reason=FinishedReason.ANSWER_TIME_REACHED)
        return None
    if isinstance(config, ModelDecidesConfig):
        return await _model_decides(config, len(turns), llm)
    raise TypeError(f"Unsupported interview rule: {type(config).__name__}")
