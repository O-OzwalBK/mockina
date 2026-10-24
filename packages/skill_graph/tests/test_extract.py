import json

import pytest
from contracts import SkillGraph, skill_id
from llm_gateway import (
    Completion,
    ContextBudgetExceededError,
    LLMAuthError,
    LLMConnectionError,
    LLMRateLimitError,
    LLMRequestError,
    LLMResponseError,
    LLMServerError,
    LLMTimeoutError,
)
from llm_gateway.testing import FakeLLM
from skill_graph.extract import (
    SkillExtractionError,
    SkillParseError,
    extract_skills,
    parse_skill_tree,
)
from skill_graph.store import InMemorySkillCatalog


@pytest.fixture
def anyio_backend():
    """Run asynchronous extraction tests on asyncio only."""
    return "asyncio"


def valid_reply() -> dict[str, object]:
    """Return a small nested model reply with three technical leaves."""
    return {
        "categories": [
            {
                "label": "React",
                "skills": [
                    {"label": "hooks", "importance": 4, "difficulty": 2},
                    {"label": "routing", "importance": 3, "difficulty": 3},
                    {"label": "state", "importance": 5, "difficulty": 3},
                ],
            }
        ]
    }


def completion(data: object, *, finish_reason: str | None = "stop") -> Completion:
    """Serialize a value as the model's reply with a configurable stop reason."""
    return Completion(text=json.dumps(data), model="fake-model", finish_reason=finish_reason)


def test_parse_skill_tree_flattens_nested_nodes_and_computes_stable_ids():
    """Nested model output becomes a flat graph whose IDs are computed by contracts."""
    graph = parse_skill_tree(valid_reply())
    root = next(node for node in graph.nodes if node.parent_id is None)
    hooks = next(node for node in graph.nodes if node.label == "hooks")

    assert root.id == skill_id("React", "React")
    assert hooks.id == skill_id("React", "hooks")
    assert hooks.parent_id == root.id
    assert hooks.importance == 4
    assert hooks.difficulty == 2


def test_parse_skill_tree_preserves_depth_three_without_leaf_metadata_on_middle_nodes():
    """A useful intermediate node is flattened while only its descendants carry metadata."""
    reply = {
        "categories": [
            {
                "label": "React",
                "skills": [
                    {
                        "label": "routing",
                        "skills": [
                            {"label": "react router", "importance": 2, "difficulty": 2},
                            {"label": "nested routing", "importance": 3, "difficulty": 3},
                            {"label": "route guards", "importance": 4, "difficulty": 3},
                        ],
                    }
                ],
            }
        ]
    }
    graph = parse_skill_tree(reply)
    middle = next(node for node in graph.nodes if node.label == "routing")
    leaf = next(node for node in graph.nodes if node.label == "react router")
    assert middle.importance is None
    assert middle.difficulty is None
    assert leaf.parent_id == middle.id


@pytest.mark.parametrize(
    "data",
    [None, [], {}, {"categories": []}, {"categories": "React"}, {"other": []}],
)
def test_parse_skill_tree_rejects_missing_or_wrong_nested_shapes(data):
    """Missing, empty, or wrongly typed category structures are repairable parse errors."""
    with pytest.raises(SkillParseError):
        parse_skill_tree(data)


def test_parse_skill_tree_rejects_metadata_on_an_intermediate_node():
    """A nested node with children cannot also carry leaf-only importance or difficulty."""
    reply = valid_reply()
    reply["categories"][0]["skills"][0]["skills"] = [
        {"label": "nested", "importance": 2, "difficulty": 2}
    ]
    with pytest.raises(SkillParseError):
        parse_skill_tree(reply)


@pytest.mark.anyio
async def test_invalid_json_gets_one_repair_call_and_then_returns_the_graph():
    """One unparseable reply may be repaired once with bounded feedback."""
    fake = FakeLLM("not JSON", completion(valid_reply()))
    catalog = InMemorySkillCatalog(seed_entries=())

    graph = await extract_skills(
        fake,
        catalog,
        owner_id="alice",
        job_title="React Developer",
        job_description="Build web interfaces.",
    )

    assert isinstance(graph, SkillGraph)
    assert len(fake.calls) == 2
    assert "not JSON" in fake.calls[1].messages[-1].content


@pytest.mark.anyio
async def test_invalid_graph_gets_one_graph_repair_call():
    """A structurally invalid graph may be repaired once after valid JSON parsing."""
    invalid = valid_reply()
    invalid["categories"][0]["skills"].pop()
    fake = FakeLLM(completion(invalid), completion(valid_reply()))
    catalog = InMemorySkillCatalog(seed_entries=())

    graph = await extract_skills(
        fake,
        catalog,
        owner_id="alice",
        job_title="React Developer",
        job_description="Build web interfaces.",
    )

    assert isinstance(graph, SkillGraph)
    assert len(fake.calls) == 2
    assert "graph" in fake.calls[1].messages[-1].content.lower()


@pytest.mark.anyio
async def test_parse_then_graph_repair_uses_no_more_than_three_model_calls():
    """Extraction can use at most one parse repair and one graph repair call."""
    invalid = valid_reply()
    invalid["categories"][0]["skills"].pop()
    fake = FakeLLM("not JSON", completion(invalid), completion(valid_reply()))
    catalog = InMemorySkillCatalog(seed_entries=())

    graph = await extract_skills(
        fake,
        catalog,
        owner_id="alice",
        job_title="React Developer",
        job_description="Build web interfaces.",
    )

    assert isinstance(graph, SkillGraph)
    assert len(fake.calls) == 3


@pytest.mark.anyio
async def test_truncated_reply_fails_without_a_repair_call():
    """A length-stopped reply is a configuration failure and is never repaired."""
    fake = FakeLLM(completion(valid_reply(), finish_reason="length"), completion(valid_reply()))

    with pytest.raises(SkillExtractionError):
        await extract_skills(
            fake,
            InMemorySkillCatalog(seed_entries=()),
            owner_id="alice",
            job_title="React Developer",
            job_description="Build web interfaces.",
        )

    assert len(fake.calls) == 1
    assert fake.remaining == 1


@pytest.mark.anyio
@pytest.mark.parametrize(
    "error",
    [
        ContextBudgetExceededError("too long"),
        LLMAuthError("bad key"),
        LLMConnectionError("offline"),
        LLMRateLimitError("busy"),
        LLMRequestError("bad request"),
        LLMResponseError("bad response"),
        LLMServerError("server issue"),
        LLMTimeoutError("slow"),
    ],
)
async def test_gateway_errors_pass_through_without_repair(error):
    """Every gateway error keeps its type and is not mistaken for a parse failure."""
    fake = FakeLLM(error, completion(valid_reply()))
    with pytest.raises(type(error)) as caught:
        await extract_skills(
            fake,
            InMemorySkillCatalog(seed_entries=()),
            owner_id="alice",
            job_title="React Developer",
            job_description="Build web interfaces.",
        )
    assert caught.value is error
    assert len(fake.calls) == 1
