"""What the engine returns: the next question, or why the interview is over."""

from enum import StrEnum

from contracts import ImmutableModel, Question
from pydantic import Field


class FinishedReason(StrEnum):
    """Why the engine stopped asking new questions.

    - question_count_reached: code reached the configured number of questions.
    - answer_time_reached: the answered turns used up the configured answering time.
    - model_decided: the model chose to finish inside the allowed question range.
    """

    QUESTION_COUNT_REACHED = "question_count_reached"
    ANSWER_TIME_REACHED = "answer_time_reached"
    MODEL_DECIDED = "model_decided"


class InterviewFinished(ImmutableModel):
    """The engine has no new question: the interview is over, and this is why."""

    reason: FinishedReason = Field(
        description="Why the interview ended.",
        examples=["question_count_reached"],
    )


# A turn's opening move: a new question, or the news that the interview is over.
EngineOutcome = Question | InterviewFinished
