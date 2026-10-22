from typing import Any

from pydantic import BaseModel

import contracts

# Models that clients only send and the server never returns. Their schema describes what a client may leave out. Every other model is described as the server sends it.
REQUEST_ONLY_MODELS = frozenset({"PreparationCreate"})


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
    A model the server sends back (not listed in REQUEST_ONLY_MODELS) is described in
    "serialization" mode, where every field is required, because the server always includes
    all of them, even those with a default. A model clients only send is described in
    "validation" mode, where fields with a default may be left out.
    """
    return {
        name: model.model_json_schema(
            mode="validation" if name in REQUEST_ONLY_MODELS else "serialization"
        )
        for name, model in sorted(public_models().items())
        if model.model_fields
    }
