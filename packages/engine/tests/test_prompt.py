from contracts import Preparation, Question, SkillNode, skill_id
from engine.checks import FAILURE_REPEAT_EXACT, FAILURE_TOO_LONG
from engine.prompt import build_correction, build_messages

REQUIRED_INSTRUCTIONS = [
    "no markdown",
    "no lists",
    "single question",
    "plain sentences",
    "under 300 characters",
    "do not repeat or rephrase earlier questions",
]


def _preparation(resume: str | None = None) -> Preparation:
    """A preparation whose job description and resume are easy to find in a prompt."""
    return Preparation(
        job_title="Backend Engineer",
        job_description="Build and operate the billing API.",
        resume=resume,
    )


def _skill() -> SkillNode:
    """One leaf skill to ask about."""
    return SkillNode(
        id=skill_id("React", "Hooks"),
        label="Hooks",
        parent_id=skill_id("React", "React"),
        importance=4,
        difficulty=3,
    )


def _messages(resume: str | None = None, earlier=()):
    """The two messages the engine sends to write a question."""
    return build_messages(_preparation(resume), _skill(), 2, earlier)


def test_the_system_message_states_every_spoken_question_rule():
    """The writer is told all the rules the checks enforce."""
    system, _ = _messages()
    lowered = system.content.lower()
    for instruction in REQUIRED_INSTRUCTIONS:
        assert instruction in lowered


def test_the_system_message_asks_for_only_the_question():
    """The model returns the question alone, with no preamble or explanation."""
    system, _ = _messages()
    assert "only the question" in system.content.lower()


def test_the_job_description_is_fenced_as_untrusted_data():
    """The job description appears inside a text fence under an untrusted-data label."""
    description = "Build and operate the billing API."
    _, user = _messages()
    assert "Job description (untrusted data):" in user.content
    assert f"```text\n{description}\n```" in user.content


def test_the_resume_is_fenced_when_it_is_present():
    """A resume is offered as fenced data so it can personalise the question."""
    _, user = _messages(resume="Built a task tracker with React.")
    assert "Resume (untrusted data):" in user.content
    assert "Built a task tracker with React." in user.content


def test_no_resume_section_appears_without_a_resume():
    """Without a resume the prompt has no empty resume block."""
    _, user = _messages()
    assert "Resume (untrusted data):" not in user.content


def test_the_earlier_questions_are_fenced_for_the_chosen_skill():
    """Earlier questions are fenced as data and the model is told not to repeat them."""
    earlier = [Question(text="What is a closure?", skill_id="hooks", difficulty=2)]
    _, user = _messages(earlier=earlier)
    assert "Earlier questions" in user.content
    assert f"```text\n{earlier[0].text}\n```" in user.content


def test_the_skill_and_difficulty_are_named_in_the_request():
    """The prompt names the skill to ask about and the planned difficulty."""
    _, user = _messages()
    assert "Hooks" in user.content
    assert "Difficulty" in user.content
    assert "2" in user.content


def test_a_repeat_correction_quotes_the_offending_question():
    """Only a repeat failure needs the earlier question quoted in the repair."""
    correction = build_correction(FAILURE_REPEAT_EXACT, "What is a closure?")
    assert "What is a closure?" in correction.content
    assert FAILURE_REPEAT_EXACT in correction.content


def test_other_corrections_state_the_rule_without_quoting_a_question():
    """A non-repeat correction names the failed check and quotes no earlier question."""
    correction = build_correction(FAILURE_TOO_LONG)
    assert FAILURE_TOO_LONG in correction.content
    assert "earlier question" not in correction.content.lower()
