from enum import Enum

import contracts
import pytest
from contracts.schemas import public_models

EXPECTED_PUBLIC_NAMES = {
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
}

EXPORTED = [getattr(contracts, name) for name in contracts.__all__]
PUBLIC_ENUMS = [item for item in EXPORTED if isinstance(item, type) and issubclass(item, Enum)]
PUBLIC_MODELS = list(public_models().values())


def test_public_names_are_exactly_the_expected_ones():
    """The public API changes only on purpose: adding or removing an exported name means updating this list."""
    assert set(contracts.__all__) == EXPECTED_PUBLIC_NAMES


@pytest.mark.parametrize("item", PUBLIC_MODELS + PUBLIC_ENUMS, ids=lambda item: item.__name__)
def test_every_public_class_has_a_docstring(item):
    """Every public model and enum has its own docstring, so generated documentation is never empty."""
    assert item.__doc__ is not None
    assert item.__doc__.strip() != ""


@pytest.mark.parametrize("model", PUBLIC_MODELS, ids=lambda model: model.__name__)
def test_every_public_model_field_has_a_description(model):
    """Every field of every public model has a description, so generated documentation has no gaps."""
    undocumented = [name for name, field in model.model_fields.items() if not field.description]
    assert undocumented == []
