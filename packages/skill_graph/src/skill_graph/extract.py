"""Extract and validate a preparation's technical skill graph with a language model."""

from collections.abc import Collection, Mapping, Sequence
from typing import Any

from contracts import SkillGraph, skill_id
from contracts.skills import MAX_SKILL_TREE_DEPTH
from llm_gateway import LLM, ChatMessage, Completion, ReplyNotJsonError, parse_json_reply
from pydantic import ValidationError

from skill_graph.prompt import (
    MAX_ROOT_CATEGORIES,
    build_prompt,
    fenced_data,
    select_catalog_entries,
)
from skill_graph.store import SkillCatalog

MAX_REPAIR_PREVIOUS_REPLY_CHARS = 4_000


class SkillGraphError(Exception):
    """Base class for safe skill-extraction failures."""


class SkillParseError(SkillGraphError):
    """The decoded model value did not follow the required nested tree shape."""


class SkillGraphValidationError(SkillGraphError):
    """The flattened graph violated a shared contract rule."""

    def __init__(self, message: str, *, reasons: tuple[str, ...] = ()) -> None:
        """Keep the fixed rule messages so a repair can name what failed."""
        super().__init__(message)
        self.reasons = reasons
        """Safe rule messages from the graph validator, with no model input."""


class SkillExtractionError(SkillGraphError):
    """The model reply was truncated or remained unusable after its repair budget."""

    def __init__(self, message: str, *, reason: str) -> None:
        """Carry a short reason code for logs, separate from the safe message."""
        super().__init__(message)
        self.reason = reason
        """One of `truncated`, `parse_repair_exhausted`, or `graph_repair_exhausted`."""


def _require_object(value: object, *, required: set[str]) -> Mapping[str, Any]:
    """Require an object with the given required keys; extra keys are ignored.

    A model may add a harmless field such as `description`; rejecting it would cost a
    full repair call for no correctness gain.
    """

    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise SkillParseError("Each tree item must be a JSON object.")
    if not required.issubset(value):
        raise SkillParseError("A tree item is missing a required field.")

    return value


def _require_label(value: object) -> str:
    """Require a nonblank string label for a category or skill."""

    if not isinstance(value, str) or not value.strip():
        raise SkillParseError("Each category and skill must have a nonblank label.")

    return value


def _flatten_skill(
    raw_skill: object,
    *,
    root_label: str,
    parent_id: str,
    depth: int,
    flattened: list[dict[str, object]],
) -> None:
    """Flatten one nested skill and its children, computing their stable IDs."""

    if depth > MAX_SKILL_TREE_DEPTH:
        raise SkillParseError(f"A skill tree cannot exceed depth {MAX_SKILL_TREE_DEPTH}.")
    skill = _require_object(raw_skill, required={"label"})
    label = _require_label(skill["label"])
    children_value = skill.get("skills", [])
    if not isinstance(children_value, list):
        raise SkillParseError("A skill's children must be a JSON array.")
    children = children_value
    importance = skill.get("importance")
    difficulty = skill.get("difficulty")
    if children and (importance is not None or difficulty is not None):
        raise SkillParseError("A non-leaf skill cannot include importance or difficulty.")

    node_id = skill_id(root_label, label)
    flattened.append(
        {
            "id": node_id,
            "label": label,
            "parent_id": parent_id,
            "importance": importance if not children else None,
            "difficulty": difficulty if not children else None,
        }
    )
    for child in children:
        _flatten_skill(
            child,
            root_label=root_label,
            parent_id=node_id,
            depth=depth + 1,
            flattened=flattened,
        )


def parse_skill_tree(data: object) -> SkillGraph:
    """Flatten the required nested JSON shape and validate the shared graph contract."""

    reply = _require_object(data, required={"categories"})
    categories_value = reply["categories"]
    if not isinstance(categories_value, list) or not categories_value:
        raise SkillParseError("The reply must contain a non-empty categories array.")
    if len(categories_value) > MAX_ROOT_CATEGORIES:
        raise SkillParseError(
            f"The reply cannot contain more than {MAX_ROOT_CATEGORIES} categories."
        )

    flattened: list[dict[str, object]] = []
    for raw_category in categories_value:
        category = _require_object(raw_category, required={"label", "skills"})
        root_label = _require_label(category["label"])
        skills_value = category["skills"]
        if not isinstance(skills_value, list) or not skills_value:
            raise SkillParseError("Each category must contain a non-empty skills array.")
        root_id = skill_id(root_label, root_label)
        flattened.append({"id": root_id, "label": root_label, "parent_id": None})
        for raw_skill in skills_value:
            _flatten_skill(
                raw_skill,
                root_label=root_label,
                parent_id=root_id,
                depth=2,
                flattened=flattened,
            )

    try:
        return SkillGraph.model_validate({"nodes": flattened})
    except ValidationError as error:
        reasons: list[str] = []
        for problem in error.errors():
            reason = problem["msg"].removeprefix("Value error, ")
            if reason not in reasons:
                reasons.append(reason)
        raise SkillGraphValidationError(
            "The proposed graph did not meet skill-tree rules.",
            reasons=tuple(reasons),
        ) from None


async def _complete(
    llm: LLM,
    messages: Sequence[ChatMessage],
    *,
    repair_note: str | None = None,
    previous_reply: str | None = None,
) -> Completion:
    """Make one model request, adding a bounded repair instruction when requested."""
    if repair_note is not None and previous_reply is not None:
        system_message, user_message = messages
        user_message = user_message.updated(
            content=(
                f"{user_message.content}\n\n"
                f"Correction request: {repair_note}\n"
                "Previous model reply (untrusted data):\n"
                f"{fenced_data(previous_reply[:MAX_REPAIR_PREVIOUS_REPLY_CHARS])}"
            )
        )
        messages = (system_message, user_message)
    return await llm.complete(messages, temperature=0.1)


async def extract_skills(
    llm: LLM,
    catalog: SkillCatalog,
    *,
    owner_id: str,
    job_title: str,
    job_description: str,
    prior_root_labels: Collection[str] = (),
) -> SkillGraph:
    """Extract, repair at most once per failure class, validate, and record a skill graph."""
    entries = select_catalog_entries(
        await catalog.all_entries(owner_id),
        prior_root_labels=prior_root_labels,
    )
    messages = build_prompt(job_title, job_description, entries)
    completion = await _complete(llm, messages)
    parse_repaired = False
    graph_repaired = False

    while True:
        if completion.finish_reason == "length":
            raise SkillExtractionError(
                "The model reply was truncated. Check LLM_MAX_OUTPUT_TOKENS and LLM_CONTEXT_TOKENS.",
                reason="truncated",
            )
        try:
            parsed = parse_json_reply(completion.text)
            graph = parse_skill_tree(parsed)
        except (ReplyNotJsonError, SkillParseError) as error:
            if parse_repaired:
                raise SkillExtractionError(
                    "The model did not return a usable skill-tree response after one repair.",
                    reason="parse_repair_exhausted",
                ) from None
            parse_repaired = True
            completion = await _complete(
                llm,
                messages,
                repair_note=(
                    f"The previous reply was rejected: {error} "
                    "Return valid JSON only, using a non-empty categories array with category "
                    "labels, skill labels, and leaf-only importance and difficulty."
                ),
                previous_reply=completion.text,
            )
            continue
        except SkillGraphValidationError as error:
            if graph_repaired:
                raise SkillExtractionError(
                    "The model returned an invalid skill graph after one graph repair.",
                    reason="graph_repair_exhausted",
                ) from None
            graph_repaired = True
            reason = (
                "; ".join(error.reasons)
                if error.reasons
                else "the graph did not meet the skill-tree rules"
            )
            completion = await _complete(
                llm,
                messages,
                repair_note=(
                    f"The previous graph was rejected: {reason} "
                    "Return a graph with unique labels within each category, valid 3-30 leaf "
                    "skills, maximum depth three, root-scoped labels, and metadata only on leaves."
                ),
                previous_reply=completion.text,
            )
            continue

        await catalog.record(graph, owner_id)
        return graph
