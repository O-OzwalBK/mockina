import inspect
from typing import get_args

import engine
from contracts import Question
from engine import EngineOutcome, InterviewFinished
from pydantic import BaseModel

EXPECTED_PUBLIC_NAMES = {
    "EngineOutcome",
    "EngineSettings",
    "FinishedReason",
    "InterviewFinished",
    "UnusableQuestionError",
    "next_turn",
}


def test_public_names_are_exactly_the_expected_ones():
    """The public API changes only on purpose: adding or removing an export updates this list."""
    assert set(engine.__all__) == EXPECTED_PUBLIC_NAMES


def test_every_exported_model_documents_itself_and_its_fields():
    """Every exported Pydantic model has a docstring and a description on every field."""
    for name in engine.__all__:
        item = getattr(engine, name)
        if not (isinstance(item, type) and issubclass(item, BaseModel)):
            continue
        assert item.__doc__ is not None
        assert item.__doc__.strip() != ""
        assert all(field.description for field in item.model_fields.values()), name


def test_next_turn_is_the_async_entry_point():
    """The package's one function is asynchronous, because it may call the model."""
    assert inspect.iscoroutinefunction(engine.next_turn)


def test_engine_outcome_is_the_question_or_finished_union():
    """The outcome type has exactly the two arms callers handle."""
    assert set(get_args(EngineOutcome)) == {Question, InterviewFinished}
