from copy import deepcopy
from typing import Any
from unicodedata import normalize as unicode_normalize

import pytest
from contracts.skills import (
    MAX_SKILL_TREE_DEPTH,
    SkillGraph,
    normalize,
    normalize_sorted,
    skill_id,
)
from pydantic import ValidationError


def valid_skill_graph_data() -> dict[str, Any]:
    """Return a fresh depth-three graph with three scored skill leaves."""
    root_id = skill_id("React", "React")
    hooks_id = skill_id("React", "Hooks")
    return {
        "nodes": [
            {"id": root_id, "label": "React", "parent_id": None},
            {"id": hooks_id, "label": "Hooks", "parent_id": root_id},
            {
                "id": skill_id("React", "Custom hooks"),
                "label": "Custom hooks",
                "parent_id": hooks_id,
                "importance": 4,
                "difficulty": 3,
            },
            {
                "id": skill_id("React", "Effect hooks"),
                "label": "Effect hooks",
                "parent_id": hooks_id,
                "importance": 3,
                "difficulty": 2,
            },
            {
                "id": skill_id("React", "Built-in hooks"),
                "label": "Built-in hooks",
                "parent_id": hooks_id,
                "importance": 2,
                "difficulty": 1,
            },
        ]
    }


def test_normalize_uses_nfkc_lowercase_and_punctuation_spaces():
    """Visually equivalent Unicode and punctuation variants share a normalized label."""
    assert normalize("Node.js") == normalize("node js")
    assert normalize("react_hooks") == normalize("react hooks")
    assert normalize("C++") != normalize("C")
    assert normalize("C#") != normalize("C")
    assert normalize(unicode_normalize("NFC", "नमस्ते")) == normalize(
        unicode_normalize("NFD", "नमस्ते")
    )


def test_normalize_sorted_drops_only_the_agreed_stopwords():
    """The canonical skill label ignores order and listed stopwords but preserves negation."""
    assert normalize_sorted("react hooks") == normalize_sorted("hooks in react")
    assert normalize_sorted("hooks with no mocks") != normalize_sorted("hooks with mocks")
    assert normalize_sorted("in the and") == ""


def test_skill_id_is_pinned_and_scoped_to_the_root():
    """The namespace and canonicalization are a stable contract, scoped by root label."""
    assert skill_id("React", "hooks") == "8dd8e540-014e-52e3-8f87-0fd42abe1678"
    assert skill_id("React", "hooks") == skill_id("React", "react hooks")
    assert skill_id("React", "hooks") == skill_id("React", "hooks in react")
    assert skill_id("React", "custom hooks") == skill_id("React", "hooks custom")
    assert skill_id("React", "Node.js") == skill_id("React", "node js")
    assert skill_id("React", "react_hooks") == skill_id("React", "react hooks")
    assert skill_id("React", "React Native") != skill_id("React", "native")
    assert skill_id("React", "React Router") != skill_id("React", "router")
    assert skill_id("React", "React Query") != skill_id("React", "query")
    assert skill_id("Vue", "Vue Router") != skill_id("Vue", "router")
    assert skill_id("Angular", "Angular Router") != skill_id("Angular", "router")
    assert skill_id("Next.js", "Next.js") != skill_id("Next.js", "js")
    assert skill_id("Svelte", "Svelte Kit") != skill_id("Svelte", "kit")
    assert skill_id("React", "custom hooks") != skill_id("Vue", "custom hooks")
    assert skill_id("React", "C++") != skill_id("React", "C")
    assert skill_id("React", "C#") != skill_id("React", "C")
    assert skill_id("React", "F#") != skill_id("React", "F")


def test_skill_graph_accepts_a_depth_three_tree_and_leaf_metadata():
    """A preparation may use depth three while only leaves carry importance and difficulty."""
    graph = SkillGraph.model_validate(valid_skill_graph_data())
    assert len(graph.nodes) == 5
    assert MAX_SKILL_TREE_DEPTH == 3


def test_same_skill_id_is_valid_at_depth_two_or_three():
    """A node's depth does not participate in its root-scoped identity."""
    depth_three = valid_skill_graph_data()
    depth_two = deepcopy(depth_three)
    depth_two["nodes"].pop(1)
    root_id = depth_two["nodes"][0]["id"]
    for node in depth_two["nodes"][1:]:
        node["parent_id"] = root_id

    first_graph = SkillGraph.model_validate(depth_three)
    second_graph = SkillGraph.model_validate(depth_two)
    first_root = next(node for node in first_graph.nodes if node.parent_id is None)
    assert first_root.id == skill_id("React", "React")
    first_leaf = next(node for node in first_graph.nodes if node.label == "Custom hooks")
    second_leaf = next(node for node in second_graph.nodes if node.label == "Custom hooks")
    assert first_leaf.id == second_leaf.id


@pytest.mark.parametrize("difficulty", [0, 6])
def test_skill_node_rejects_difficulty_outside_one_to_five(difficulty):
    """A provided per-preparation skill difficulty must be from one through five."""
    data = valid_skill_graph_data()
    data["nodes"][2]["difficulty"] = difficulty
    with pytest.raises(ValidationError):
        SkillGraph.model_validate(data)


@pytest.mark.parametrize("importance", [0, 6])
def test_skill_node_rejects_importance_outside_one_to_five(importance):
    """A provided importance value must be from one through five."""
    data = valid_skill_graph_data()
    data["nodes"][2]["importance"] = importance
    with pytest.raises(ValidationError):
        SkillGraph.model_validate(data)


def test_skill_graph_rejects_metadata_on_a_non_leaf():
    """Category and intermediate nodes cannot carry per-preparation leaf metadata."""
    data = valid_skill_graph_data()
    data["nodes"][1]["importance"] = 2
    data["nodes"][1]["difficulty"] = 2
    with pytest.raises(ValidationError):
        SkillGraph.model_validate(data)


def test_skill_graph_requires_both_metadata_fields_on_each_leaf():
    """Every leaf has both importance and difficulty, rather than only one or neither."""
    data = valid_skill_graph_data()
    del data["nodes"][2]["importance"]
    with pytest.raises(ValidationError):
        SkillGraph.model_validate(data)


def test_skill_graph_rejects_depth_greater_than_three():
    """The tree can reach depth three but no deeper."""
    data = valid_skill_graph_data()
    data["nodes"].append(
        {
            "id": skill_id("React", "Advanced hooks"),
            "label": "Advanced hooks",
            "parent_id": data["nodes"][2]["id"],
            "importance": 2,
            "difficulty": 3,
        }
    )
    with pytest.raises(ValidationError):
        SkillGraph.model_validate(data)


def test_skill_graph_rejects_a_missing_parent():
    """Every non-root node refers to a node in the same graph."""
    data = valid_skill_graph_data()
    data["nodes"][1]["parent_id"] = "missing-parent"
    with pytest.raises(ValidationError):
        SkillGraph.model_validate(data)


def test_skill_graph_rejects_an_id_that_does_not_match_its_root_and_label():
    """Every node ID is recomputed from its root and canonical label."""
    data = valid_skill_graph_data()
    data["nodes"][2]["id"] = skill_id("React", "different skill")
    with pytest.raises(ValidationError):
        SkillGraph.model_validate(data)


def test_skill_graph_requires_three_to_thirty_leaf_skills():
    """A graph has three to thirty leaves, without enforcing prompt targets."""
    too_few = valid_skill_graph_data()
    too_few["nodes"] = too_few["nodes"][:3]
    with pytest.raises(ValidationError):
        SkillGraph.model_validate(too_few)

    too_many = valid_skill_graph_data()
    too_many["nodes"].extend(
        [
            {
                "id": skill_id("React", f"Skill {index}"),
                "label": f"Skill {index}",
                "parent_id": too_many["nodes"][1]["id"],
                "importance": 3,
                "difficulty": 2,
            }
            for index in range(28)
        ]
    )
    with pytest.raises(ValidationError):
        SkillGraph.model_validate(too_many)


def test_skill_graph_rejects_duplicate_sibling_labels():
    """Siblings with labels differing only by canonical punctuation are duplicates."""
    data = valid_skill_graph_data()
    data["nodes"][3]["label"] = "Custom_hooks"
    data["nodes"][3]["id"] = skill_id("React", "Custom_hooks")
    with pytest.raises(ValidationError):
        SkillGraph.model_validate(data)


def test_skill_graph_rejects_duplicate_node_ids():
    """A graph contains one node for each root-scoped skill ID."""
    data = valid_skill_graph_data()
    data["nodes"].append(deepcopy(data["nodes"][2]))
    with pytest.raises(ValidationError):
        SkillGraph.model_validate(data)


def test_skill_graph_rejects_a_leaf_matching_its_parent_label():
    """A leaf and its parent cannot have the same canonical label."""
    data = valid_skill_graph_data()
    data["nodes"][2]["label"] = "Hooks"
    data["nodes"][2]["id"] = skill_id("React", "Hooks")
    with pytest.raises(ValidationError):
        SkillGraph.model_validate(data)


def test_skill_node_rejects_a_label_with_only_stopwords():
    """A label that canonicalizes to no tokens cannot identify a skill node."""
    data = valid_skill_graph_data()
    data["nodes"][2]["label"] = "in the"
    data["nodes"][2]["id"] = skill_id("React", "in the")
    with pytest.raises(ValidationError):
        SkillGraph.model_validate(data)
