from datetime import UTC, datetime, timedelta

import pytest
from contracts import SkillGraph, skill_id
from skill_graph.prompt import MAX_CATALOG_ENTRIES_IN_PROMPT
from skill_graph.store import (
    SEED_CATALOG,
    InMemorySkillCatalog,
    InMemorySkillStore,
    SkillCatalog,
)


@pytest.fixture
def anyio_backend():
    """Run asynchronous catalog tests on asyncio only."""
    return "asyncio"


def graph_with_leaf(label: str) -> SkillGraph:
    """Build a graph with one root and three leaves, including the named skill."""
    root_label = "React"
    root_id = skill_id(root_label, root_label)
    labels = [label, "Effect hooks", "Built-in hooks"]
    return SkillGraph.model_validate(
        {
            "nodes": [
                {"id": root_id, "label": root_label, "parent_id": None},
                *[
                    {
                        "id": skill_id(root_label, leaf_label),
                        "label": leaf_label,
                        "parent_id": root_id,
                        "importance": 3,
                        "difficulty": 2,
                    }
                    for leaf_label in labels
                ],
            ]
        }
    )


def test_seed_catalog_contains_the_documented_common_technologies():
    """The initial prompt has common catalog labels even before any extraction is recorded."""
    labels = {entry.node_label for entry in SEED_CATALOG}
    assert labels == {
        "JavaScript",
        "TypeScript",
        "Python",
        "SQL",
        "React",
        "Vue",
        "Node.js",
        "Docker",
        "Kubernetes",
        "PostgreSQL",
        "MongoDB",
        "Git",
    }


def test_seed_catalog_fits_inside_the_prompt_cap():
    """A future seed addition cannot make the catalog impossible to select."""
    assert len(SEED_CATALOG) <= MAX_CATALOG_ENTRIES_IN_PROMPT


@pytest.mark.anyio
async def test_all_entries_are_sorted_by_creation_time_then_id():
    """Catalog ordering is stable so repeated prompts do not drift with dict order."""
    first_time = datetime(2026, 10, 23, tzinfo=UTC)
    second_time = first_time + timedelta(seconds=1)
    moments = iter([first_time, second_time])
    catalog = InMemorySkillCatalog(clock=lambda: next(moments))
    await catalog.record(graph_with_leaf("Hooks"))
    await catalog.record(graph_with_leaf("State hooks"))

    entries = await catalog.all_entries()
    assert list(entries) == sorted(entries, key=lambda entry: (entry.created_at, entry.id))


@pytest.mark.anyio
async def test_record_keeps_first_sighting_label_and_timestamp():
    """Recording an existing ID is idempotent and does not replace first-seen data."""
    first_time = datetime(2026, 10, 23, tzinfo=UTC)
    later_time = first_time + timedelta(days=1)
    moments = iter([first_time, later_time])
    catalog = InMemorySkillCatalog(clock=lambda: next(moments))
    await catalog.record(graph_with_leaf("hooks"))
    await catalog.record(graph_with_leaf("react hooks"))

    hooks_id = skill_id("React", "hooks")
    entries = await catalog.all_entries()
    entry = next(entry for entry in entries if entry.id == hooks_id)
    assert entry.node_label == "hooks"
    assert entry.created_at == first_time
    assert sum(entry.id == hooks_id for entry in entries) == 1


@pytest.mark.anyio
async def test_catalog_entries_store_the_root_but_not_preparation_metadata():
    """Catalog identity and labels are global while importance and difficulty stay per graph."""
    catalog = InMemorySkillCatalog()
    await catalog.record(graph_with_leaf("Hooks"))

    entries = await catalog.all_entries()
    entry = next(entry for entry in entries if entry.node_label == "Hooks")
    assert entry.root_label == "React"
    assert not hasattr(entry, "importance")
    assert not hasattr(entry, "difficulty")


@pytest.mark.anyio
async def test_in_memory_store_provides_the_catalog_protocol():
    """The store container exposes a catalog that extraction can depend on independently."""
    store = InMemorySkillStore()
    assert isinstance(store.catalog, SkillCatalog)
    assert await store.catalog.all_entries()
