import pytest
from contracts import Question, SkillGraph, SkillNode, Turn, skill_id
from engine.errors import EmptySkillGraphError
from engine.selection import choose_difficulty, choose_skill

ROOT_LABEL = "React"


def _graph(*, importances=(3, 3, 3), difficulties=(3, 3, 3)) -> SkillGraph:
    """A React root with three leaves in a fixed order: Hooks, State, Effects."""
    root = SkillNode(
        id=skill_id(ROOT_LABEL, ROOT_LABEL),
        label=ROOT_LABEL,
        parent_id=None,
        importance=None,
        difficulty=None,
    )
    leaves = [
        SkillNode(
            id=skill_id(ROOT_LABEL, label),
            label=label,
            parent_id=root.id,
            importance=importance,
            difficulty=difficulty,
        )
        for label, importance, difficulty in zip(
            ("Hooks", "State", "Effects"), importances, difficulties, strict=True
        )
    ]
    return SkillGraph(nodes=(root, *leaves))


def _turn(skill: str, difficulty: int = 3) -> Turn:
    """One unanswered turn for the given skill."""
    question = Question(text=f"Explain {skill}.", skill_id=skill, difficulty=difficulty)
    return Turn(question=question)


def _asked(skill: str) -> Question:
    """One earlier-session question for the given skill."""
    return Question(text=f"Explain {skill}.", skill_id=skill, difficulty=2)


def _id(label: str) -> str:
    """The stable id of a leaf under the React root."""
    return skill_id(ROOT_LABEL, label)


class LastChoice:
    """A deterministic random source that always picks the last candidate."""

    def choice(self, sequence):
        return sequence[-1]


def test_least_asked_skill_wins_even_when_its_importance_is_lower():
    """A skill asked less often is chosen over a more important but more asked one."""
    graph = _graph(importances=(5, 3, 1))
    earlier = [_asked(_id("Hooks")), _asked(_id("Hooks"))]
    chosen = choose_skill(graph, [], earlier, random_source=LastChoice())
    assert chosen.id == _id("State")


def test_equal_counts_are_broken_by_higher_importance():
    """With equal counts, the most important skill wins."""
    graph = _graph(importances=(3, 5, 4))
    chosen = choose_skill(graph, [], [], random_source=LastChoice())
    assert chosen.id == _id("State")


def test_equal_counts_and_importance_use_the_injected_random_source():
    """A complete tie is broken through the injected source, so tests are deterministic."""
    graph = _graph(importances=(3, 3, 3))
    chosen = choose_skill(graph, [], [], random_source=LastChoice())
    assert chosen.id == _id("Effects")


def test_a_skill_is_not_asked_twice_in_a_row_while_others_exist():
    """The next question moves to another skill when the last one is the top candidate again."""
    graph = _graph(importances=(5, 3, 1))
    turns = [_turn(_id("Hooks"))]
    earlier = [_asked(_id("State")), _asked(_id("Effects"))]
    chosen = choose_skill(graph, turns, earlier, random_source=LastChoice())
    assert chosen.id == _id("State")


def test_an_empty_graph_is_a_package_error_not_a_model_call():
    """The engine refuses an empty skill graph instead of asking about nothing."""
    empty = SkillGraph.model_construct(nodes=())
    with pytest.raises(EmptySkillGraphError):
        choose_skill(empty, [], [], random_source=LastChoice())


@pytest.mark.parametrize(
    ("expected", "previous_asks", "difficulty"),
    [
        (3, [], 2),
        (1, [], 1),
        (5, [], 4),
        (3, [2], 3),
        (3, [4], 4),
        (1, [1], 2),
        (5, [4], 5),
        (5, [5, 5], 5),
    ],
)
def test_difficulty_starts_below_and_rises_to_the_expected_cap(expected, previous_asks, difficulty):
    """First ask is expected minus one; re-asks rise but never pass expected plus one."""
    skill = _graph(difficulties=(expected, 3, 3)).nodes[1]
    turns = [_turn(_id("Hooks"), previous) for previous in previous_asks]
    assert choose_difficulty(skill, turns) == difficulty


def test_difficulty_is_always_at_least_one():
    """A very easy skill still starts at difficulty 1, never 0."""
    skill = _graph(difficulties=(1, 3, 3)).nodes[1]
    assert choose_difficulty(skill, []) == 1


def test_difficulty_only_reads_this_skills_earlier_asks():
    """Another skill's difficulty does not change this skill's ramp."""
    graph = _graph(difficulties=(3, 3, 3))
    skill = graph.nodes[1]
    turns = [_turn(_id("State"), 5)]
    assert choose_difficulty(skill, turns) == 2
