from typing import Any

from pydantic import BaseModel

import contracts


def public_models() -> dict[str, type[BaseModel]]:
    """Every model exported by contracts, keyed by class name."""
    models: dict[str, type[BaseModel]] = {}
    for name in contracts.__all__:
        exported = getattr(contracts, name)
        if isinstance(exported, type) and issubclass(exported, BaseModel):
            models[name] = exported
    return models


def all_schemas() -> dict[str, dict[str, Any]]:
    """The JSON schema of every public model that has fields, keyed by model name.

    Each schema is self-contained: nested models appear under "$defs". The
    descriptions, examples, and limits written on the fields all appear in it,
    so it is the machine-readable documentation of the data shapes.
    """
    return {
        name: model.model_json_schema()
        for name, model in sorted(public_models().items())
        if model.model_fields
    }
