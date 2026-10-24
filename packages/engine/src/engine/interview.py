"""The interview flow: decide whether to continue, then open the next turn."""

import random
from collections.abc import Sequence

from contracts import InterviewConfig, Preparation, Question, SkillGraph, Turn
from llm_gateway import LLM

from engine.checks import write_question
from engine.end_rules import is_finished
from engine.prompt import build_messages
from engine.results import EngineOutcome
from engine.selection import choose_difficulty, choose_skill


def _earlier_for_skill(
    skill_id: str, turns: Sequence[Turn], earlier_questions: Sequence[Question]
) -> list[Question]:
    """Every earlier question for one skill, from earlier sessions and this one."""
    questions = [question for question in earlier_questions if question.skill_id == skill_id]
    questions.extend(turn.question for turn in turns if turn.question.skill_id == skill_id)
    return questions


async def next_turn(
    preparation: Preparation,
    skill_graph: SkillGraph,
    turns: Sequence[Turn],
    earlier_questions: Sequence[Question],
    config: InterviewConfig,
    llm: LLM,
    *,
    random_source: random.Random | None = None,
) -> EngineOutcome:
    """Return the next question, or the reason the interview is already over.

    Code decides whether to stop, which skill to ask about, and the difficulty. The
    model writes only the question text. Nothing is stored and no earlier answer
    text or grade is read; only the number of answered turns and their durations
    affect the end rules.
    """
    finished = await is_finished(config, turns, llm)
    if finished is not None:
        return finished

    random_source = random_source if random_source is not None else random.Random()
    skill = choose_skill(skill_graph, turns, earlier_questions, random_source=random_source)
    difficulty = choose_difficulty(skill, turns)
    earlier = _earlier_for_skill(skill.id, turns, earlier_questions)

    messages = build_messages(preparation, skill, difficulty, earlier)
    text = await write_question(
        llm,
        messages,
        skill_id=skill.id,
        earlier_questions=earlier,
    )
    return Question(text=text, skill_id=skill.id, difficulty=difficulty)
