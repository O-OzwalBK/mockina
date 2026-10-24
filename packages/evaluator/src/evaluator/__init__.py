"""Grade one interview answer on correctness, depth, clarity, and relevance.

The evaluator is a pure function: it reads the question, the answer transcript, and
the job title it is given, asks the model once, and returns a `contracts.Evaluation`.
It stores nothing, never touches a `Turn`, and never chooses a model. Import public
names from here, for example `from evaluator import EvaluationError`.
"""

from evaluator.errors import EvaluationError

__all__ = ["EvaluationError"]
