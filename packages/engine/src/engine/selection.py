"""Choose which skill to ask about next and at what difficulty."""

import random
from collections import Counter
from collections.abc import Sequence

from contracts import Question, SkillGraph, SkillNode, Turn
from contracts.skills import MAX_DIFFICULTY, MIN_DIFFICULTY

from engine.errors import EmptySkillGraphError


def leaf_nodes(graph: SkillGraph) -> tuple[SkillNode, ...]:
    """The askable skills: nodes that are not the parent of any other node."""
    parent_ids = {node.parent_id for node in graph.nodes if node.parent_id is not None}
    return tuple(node for node in graph.nodes if node.id not in parent_ids)


def _ask_counts(turns: Sequence[Turn], earlier_questions: Sequence[Question]) -> Counter[str]:
    """How often each skill has been asked, counting earlier sessions and this one."""
    asked = [question.skill_id for question in earlier_questions]
    asked.extend(turn.question.skill_id for turn in turns)
    return Counter(asked)


def choose_skill(
    graph: SkillGraph,
    turns: Sequence[Turn],
    earlier_questions: Sequence[Question],
    *,
    random_source: random.Random,
) -> SkillNode:
    """Pick the least asked skill, then the most important, then a seeded random pick.

    The skill asked in the last turn is passed over while another leaf exists, so a
    session never asks the same skill twice in a row.
    """
    leaves = leaf_nodes(graph)
    if not leaves:
        raise EmptySkillGraphError("The skill graph has no leaf skills to ask about.")

    counts = _ask_counts(turns, earlier_questions)
    candidates = list(leaves)
    last_skill_id = turns[-1].question.skill_id if turns else None
    if len(candidates) > 1 and last_skill_id is not None:
        candidates = [node for node in candidates if node.id != last_skill_id]

    least_asked = min(counts[node.id] for node in candidates)
    candidates = [node for node in candidates if counts[node.id] == least_asked]
    highest_importance = max(node.importance or 0 for node in candidates)
    candidates = [node for node in candidates if (node.importance or 0) == highest_importance]
    return random_source.choice(candidates)


def choose_difficulty(skill: SkillNode, turns: Sequence[Turn]) -> int:
    """Start one below the expected difficulty, then rise by one but never past its cap."""
    expected = skill.difficulty
    if expected is None:
        raise ValueError("The chosen skill must have an expected difficulty.")

    previous = None
    for turn in reversed(turns):
        if turn.question.skill_id == skill.id:
            previous = turn.question.difficulty
            break

    if previous is None:
        return max(expected - 1, MIN_DIFFICULTY)
    return min(previous + 1, expected + 1, MAX_DIFFICULTY)
