import inspect

import evaluator
from evaluator import EvaluationError, grade_answer
from llm_gateway import LLMError

EXPECTED_PUBLIC_NAMES = {"EvaluationError", "grade_answer"}


def test_public_names_are_exactly_the_expected_ones():
    """The public API changes only on purpose: adding or removing an export updates this list."""
    assert set(evaluator.__all__) == EXPECTED_PUBLIC_NAMES


def test_grade_answer_is_the_async_entry_point():
    """The package exposes one asynchronous grading function."""
    assert inspect.iscoroutinefunction(grade_answer)


def test_grade_answer_requires_keyword_data_and_one_positional_model():
    """The model is passed positionally; question, answer, and job title are keyword-only."""
    parameters = inspect.signature(grade_answer).parameters
    assert list(parameters) == ["llm", "question", "answer", "job_title"]
    assert parameters["llm"].kind is inspect.Parameter.POSITIONAL_OR_KEYWORD
    for name in ("question", "answer", "job_title"):
        assert parameters[name].kind is inspect.Parameter.KEYWORD_ONLY


def test_evaluation_error_is_the_packages_only_llm_error():
    """A failed grade has one named error, and it is an LLMError for the API mapping."""
    assert issubclass(EvaluationError, LLMError)
    assert EvaluationError.retryable is False
