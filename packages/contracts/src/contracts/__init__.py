"""Shared data shapes for Mockina: the models every package and client agrees on.

This package holds data shapes and their validation rules only, with no business
logic. Import public names from here, for example `from contracts import Question`.
Size limits are constants in the module that uses them, for example
`contracts.transcript.MAX_TRANSCRIPT_LENGTH`.
"""

from contracts.common import ImmutableModel, UtcDatetime, utc_now
from contracts.evaluation import Evaluation, MetricScore
from contracts.interviewer import Question
from contracts.preparation import Preparation, PreparationCreate
from contracts.session import InterviewSession, SessionStatus
from contracts.transcript import Answer, WordTiming
from contracts.turn import Turn, TurnStatus

__all__ = [
    "Answer",
    "Evaluation",
    "ImmutableModel",
    "InterviewSession",
    "MetricScore",
    "Preparation",
    "PreparationCreate",
    "Question",
    "SessionStatus",
    "Turn",
    "TurnStatus",
    "UtcDatetime",
    "WordTiming",
    "utc_now",
]
