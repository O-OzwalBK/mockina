"""Ask the next interview question, or say that the interview is over.

The engine is a pure function: it reads the preparation, skill graph, turns, and
configuration it is given, and stores nothing. Code chooses whether to continue,
which skill to ask about, and the difficulty; the model writes only the question
text. Import public names from here, for example `from engine import FinishedReason`.
"""

from engine.errors import UnusableQuestionError
from engine.results import EngineOutcome, FinishedReason, InterviewFinished

__all__ = [
    "EngineOutcome",
    "FinishedReason",
    "InterviewFinished",
    "UnusableQuestionError",
]
