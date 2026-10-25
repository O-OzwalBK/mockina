import asyncio
from datetime import timedelta
from uuid import uuid4

import pytest
from contracts import (
    Answer,
    Evaluation,
    MetricScore,
    PreparationCreate,
    Question,
    SessionStatus,
    SkillGraph,
    SkillNode,
    TurnStatus,
    skill_id,
)
from session_store import (
    InMemorySessionStore,
    InvalidStateError,
    NotFoundError,
    OpenQuestionError,
    PreparationLockedError,
    SessionFullError,
)
from session_store.models import AwaitingGrade


async def user(store: InMemorySessionStore, token: str = "token-a"):
    """Create one user."""
    return await store.create_user(token)


def preparation_data(title: str = "Backend Engineer") -> PreparationCreate:
    """Valid preparation input."""
    return PreparationCreate(
        job_title=title,
        job_description="Build and operate backend services.",
        resume="Built a task tracker.",
    )


def question(number: int = 1, skill: str = "fastapi") -> Question:
    """A question with a fresh id."""
    return Question(
        id=uuid4(),
        text=f"Question number {number}?",
        skill_id=skill,
        difficulty=2,
    )


def answer(text: str = "A spoken answer.") -> Answer:
    """A valid answer."""
    return Answer(transcript=text, duration=10.0)


def evaluation(question_id) -> Evaluation:
    """A valid evaluation for one question."""
    metrics = {
        name: MetricScore(score=7, feedback="Reasonable.")
        for name in ("correctness", "depth", "clarity", "relevance")
    }
    return Evaluation(question_id=question_id, summary="Solid.", **metrics)


def graph() -> SkillGraph:
    """A small valid skill tree with three leaves."""
    root = SkillNode(
        id=skill_id("Backend", "Backend"),
        label="Backend",
        parent_id=None,
    )
    leaves = [
        SkillNode(
            id=skill_id("Backend", label),
            label=label,
            parent_id=root.id,
            importance=3,
            difficulty=2,
        )
        for label in ("FastAPI", "SQL", "Testing")
    ]
    return SkillGraph(nodes=(root, *leaves))


async def prepared_session(store: InMemorySessionStore, user_id):
    """Create a preparation and an empty session for it."""
    preparation = await store.create_preparation(user_id, preparation_data())
    session = await store.create_session(user_id, preparation.id)
    return preparation, session


@pytest.mark.anyio
async def test_a_user_is_created_and_found_by_its_token_hash(store):
    """The token hash is the only way to find a user; the raw token never enters the store."""
    record = await user(store)
    assert await store.get_user_by_token_hash("token-a") == record
    assert await store.get_user_by_token_hash("other") is None


@pytest.mark.anyio
async def test_touch_user_updates_last_seen_at_most_once_a_day(store, clock):
    """Auth traffic does not write the user row more than once per UTC day."""
    record = await user(store)
    clock.advance(hours=12)
    await store.touch_user(record.id)
    assert await store.get_user_by_token_hash("token-a") == record

    clock.advance(hours=13)
    await store.touch_user(record.id)
    touched = await store.get_user_by_token_hash("token-a")
    assert touched is not None
    assert touched.last_seen_at > record.last_seen_at


@pytest.mark.anyio
async def test_another_users_preparation_and_session_are_invisible(store):
    """Another owner's id behaves exactly like a missing one."""
    alice = await user(store, "alice")
    bob = await user(store, "bob")
    preparation, session = await prepared_session(store, alice.id)

    assert await store.get_preparation(bob.id, preparation.id) is None
    assert await store.get_session(bob.id, session.id) is None
    with pytest.raises(NotFoundError):
        await store.create_session(bob.id, preparation.id)


@pytest.mark.anyio
async def test_preparation_round_trip_and_summary_counts(store, clock):
    """A preparation is readable and its summary counts its sessions."""
    owner = await user(store)
    preparation = await store.create_preparation(owner.id, preparation_data())
    clock.advance(minutes=1)
    session = await store.create_session(owner.id, preparation.id)

    assert await store.get_preparation(owner.id, preparation.id) == preparation
    summaries = await store.list_preparations(owner.id)
    assert len(summaries) == 1
    assert summaries[0].session_count == 1
    assert summaries[0].last_session_at == session.updated_at


@pytest.mark.anyio
async def test_update_preparation_is_locked_after_a_session(store):
    """Editing is allowed only while no session exists."""
    owner = await user(store)
    preparation, _ = await prepared_session(store, owner.id)

    with pytest.raises(PreparationLockedError):
        await store.update_preparation(
            owner.id,
            preparation.id,
            job_title="Changed",
            job_description="Changed text.",
            resume=None,
        )


@pytest.mark.anyio
async def test_update_preparation_clears_the_skill_graph(store):
    """Editing the job text invalidates a previously extracted graph."""
    owner = await user(store)
    preparation = await store.create_preparation(owner.id, preparation_data())
    await store.save_skill_graph_if_absent(owner.id, preparation.id, graph())

    updated = await store.update_preparation(
        owner.id,
        preparation.id,
        job_title="Changed",
        job_description="Changed text.",
        resume=None,
    )

    assert updated.job_title == "Changed"
    assert await store.get_skill_graph(owner.id, preparation.id) is None


@pytest.mark.anyio
async def test_delete_preparation_removes_its_sessions(store):
    """Deleting a preparation deletes the sessions under it."""
    owner = await user(store)
    preparation, session = await prepared_session(store, owner.id)

    await store.delete_preparation(owner.id, preparation.id)

    assert await store.get_preparation(owner.id, preparation.id) is None
    assert await store.get_session(owner.id, session.id) is None


@pytest.mark.anyio
async def test_skill_graph_is_saved_only_once(store):
    """A second extraction cannot overwrite the first graph for a preparation."""
    owner = await user(store)
    preparation = await store.create_preparation(owner.id, preparation_data())
    first = graph()
    second = graph()

    saved = await store.save_skill_graph_if_absent(owner.id, preparation.id, first)
    assert saved == first
    assert await store.save_skill_graph_if_absent(owner.id, preparation.id, second) == first
    assert await store.get_skill_graph(owner.id, preparation.id) == first


@pytest.mark.anyio
async def test_list_sessions_is_newest_first_with_progress_counts(store, clock):
    """The preparation page gets each session with turns_total and turns_graded."""
    owner = await user(store)
    preparation = await store.create_preparation(owner.id, preparation_data())
    first = await store.create_session(owner.id, preparation.id)
    asked = question()
    await store.add_question(owner.id, first.id, asked)
    await store.record_answer(owner.id, first.id, asked.id, answer())
    await store.record_evaluation(owner.id, first.id, asked.id, evaluation(asked.id))
    clock.advance(minutes=1)
    second = await store.create_session(owner.id, preparation.id)

    sessions = await store.list_sessions(owner.id, preparation.id)

    assert [item.id for item in sessions] == [second.id, first.id]
    assert sessions[1].turns_total == 1
    assert sessions[1].turns_graded == 1
    assert sessions[0].turns_total == 0


@pytest.mark.anyio
async def test_create_session_starts_empty_and_in_progress(store):
    """A new session has no turns and is in progress."""
    owner = await user(store)
    _, session = await prepared_session(store, owner.id)

    assert session.status == SessionStatus.IN_PROGRESS
    assert session.turns == ()
    assert session.ended_at is None


@pytest.mark.anyio
async def test_an_open_question_is_reused_and_a_second_is_rejected(store):
    """Only one question may wait for an answer at a time."""
    owner = await user(store)
    _, session = await prepared_session(store, owner.id)
    first = question(1)
    turn = await store.add_question(owner.id, session.id, first)
    assert await store.get_open_turn(owner.id, session.id) == turn

    with pytest.raises(OpenQuestionError) as caught:
        await store.add_question(owner.id, session.id, question(2))
    assert caught.value.turn.question.id == first.id


@pytest.mark.anyio
async def test_an_answer_is_idempotent_and_a_different_body_is_invalid(store):
    """The same answer body returns the same turn; a different one is a state error."""
    owner = await user(store)
    _, session = await prepared_session(store, owner.id)
    asked = question()
    await store.add_question(owner.id, session.id, asked)
    spoken = answer()

    first = await store.record_answer(owner.id, session.id, asked.id, spoken)
    assert first.status == TurnStatus.AWAITING_GRADE
    assert await store.record_answer(owner.id, session.id, asked.id, spoken) == first

    with pytest.raises(InvalidStateError):
        await store.record_answer(owner.id, session.id, asked.id, answer("Different."))


@pytest.mark.anyio
async def test_an_evaluation_moves_the_turn_to_graded(store):
    """Recording the grade stores the evaluation and changes the status."""
    owner = await user(store)
    _, session = await prepared_session(store, owner.id)
    asked = question()
    await store.add_question(owner.id, session.id, asked)
    await store.record_answer(owner.id, session.id, asked.id, answer())

    turn = await store.record_evaluation(owner.id, session.id, asked.id, evaluation(asked.id))

    assert turn.status == TurnStatus.GRADED
    assert turn.evaluation is not None
    assert turn.evaluation.correctness.score == 7


@pytest.mark.anyio
async def test_a_grading_failure_can_be_reset_for_regrade(store):
    """A failed grade is a state that can be retried."""
    owner = await user(store)
    _, session = await prepared_session(store, owner.id)
    asked = question()
    await store.add_question(owner.id, session.id, asked)
    await store.record_answer(owner.id, session.id, asked.id, answer())

    failed = await store.record_grading_failure(
        owner.id, session.id, asked.id, "The model timed out."
    )
    assert failed.status == TurnStatus.GRADING_FAILED
    assert failed.grading_error == "The model timed out."

    reset = await store.reset_for_regrade(owner.id, session.id, asked.id)
    assert reset.status == TurnStatus.AWAITING_GRADE
    assert reset.grading_error is None


@pytest.mark.anyio
async def test_complete_drops_an_open_last_question(store):
    """Completing drops the unanswered last question and keeps answered ones."""
    owner = await user(store)
    _, session = await prepared_session(store, owner.id)
    first = question(1)
    await store.add_question(owner.id, session.id, first)
    await store.record_answer(owner.id, session.id, first.id, answer())
    await store.add_question(owner.id, session.id, question(2))

    summary = await store.complete_session(owner.id, session.id)
    saved = await store.get_session(owner.id, session.id)

    assert summary.status == SessionStatus.COMPLETED
    assert summary.turns_total == 1
    assert saved is not None
    assert saved.status == SessionStatus.COMPLETED
    assert saved.turns[-1].status == TurnStatus.AWAITING_GRADE


@pytest.mark.anyio
async def test_complete_requires_an_answered_turn(store):
    """A session with no answered turn cannot be completed."""
    owner = await user(store)
    _, session = await prepared_session(store, owner.id)

    with pytest.raises(InvalidStateError):
        await store.complete_session(owner.id, session.id)


@pytest.mark.anyio
async def test_abandon_allows_an_unanswered_session(store):
    """Abandoning does not require an answer."""
    owner = await user(store)
    _, session = await prepared_session(store, owner.id)
    await store.add_question(owner.id, session.id, question())

    summary = await store.abandon_session(owner.id, session.id)

    assert summary.status == SessionStatus.ABANDONED
    assert summary.turns_total == 1


@pytest.mark.anyio
async def test_questions_asked_covers_every_session_of_a_preparation(store, clock):
    """The engine receives questions from earlier sessions in order."""
    owner = await user(store)
    preparation = await store.create_preparation(owner.id, preparation_data())
    first_session = await store.create_session(owner.id, preparation.id)
    first = question(1)
    await store.add_question(owner.id, first_session.id, first)
    await store.record_answer(owner.id, first_session.id, first.id, answer())
    clock.advance(minutes=1)
    second_session = await store.create_session(owner.id, preparation.id)
    second = question(2)
    await store.add_question(owner.id, second_session.id, second)

    asked = await store.questions_asked(owner.id, preparation.id)
    assert asked == (first, second)


@pytest.mark.anyio
async def test_awaiting_grade_lists_turns_across_users(store):
    """The worker can find every pending turn, not only one user's."""
    alice = await user(store, "alice")
    bob = await user(store, "bob")
    _, alice_session = await prepared_session(store, alice.id)
    _, bob_session = await prepared_session(store, bob.id)
    alice_question = question(1)
    bob_question = question(2)
    await store.add_question(alice.id, alice_session.id, alice_question)
    await store.record_answer(alice.id, alice_session.id, alice_question.id, answer())
    await store.add_question(bob.id, bob_session.id, bob_question)
    await store.record_answer(bob.id, bob_session.id, bob_question.id, answer())

    pending = await store.list_awaiting_grade()
    assert {entry.question_id for entry in pending} == {
        alice_question.id,
        bob_question.id,
    }
    assert all(isinstance(entry, AwaitingGrade) for entry in pending)


@pytest.mark.anyio
async def test_two_simultaneous_questions_create_one_open_turn(store):
    """A global store lock prevents two requests from opening two questions."""
    owner = await user(store)
    _, session = await prepared_session(store, owner.id)

    results = await asyncio.gather(
        store.add_question(owner.id, session.id, question(1)),
        store.add_question(owner.id, session.id, question(2)),
        return_exceptions=True,
    )

    assert sum(isinstance(result, OpenQuestionError) for result in results) == 1
    assert sum(not isinstance(result, Exception) for result in results) == 1
    saved = await store.get_session(owner.id, session.id)
    assert saved is not None
    assert len(saved.turns) == 1


@pytest.mark.anyio
async def test_a_grading_write_and_a_new_question_do_not_lose_each_other(store):
    """Two operations on the same session merge their writes instead of replacing the session."""
    owner = await user(store)
    _, session = await prepared_session(store, owner.id)
    first = question(1)
    await store.add_question(owner.id, session.id, first)
    await store.record_answer(owner.id, session.id, first.id, answer())
    second = question(2)

    await asyncio.gather(
        store.record_evaluation(owner.id, session.id, first.id, evaluation(first.id)),
        store.add_question(owner.id, session.id, second),
    )

    saved = await store.get_session(owner.id, session.id)
    assert saved is not None
    assert len(saved.turns) == 2
    assert saved.turns[0].status == TurnStatus.GRADED
    assert saved.turns[1].question.id == second.id


@pytest.mark.anyio
async def test_a_session_cannot_exceed_one_hundred_turns(store):
    """The contract cap is enforced before the 101st question is added."""
    owner = await user(store)
    _, session = await prepared_session(store, owner.id)
    for index in range(100):
        asked = question(index)
        await store.add_question(owner.id, session.id, asked)
        await store.record_answer(owner.id, session.id, asked.id, answer())

    with pytest.raises(SessionFullError):
        await store.add_question(owner.id, session.id, question(101))


@pytest.mark.anyio
async def test_deleting_a_user_cascades_to_every_row(store):
    """Delete-my-data removes the preparations, sessions, turns, answers and evaluations."""
    owner = await user(store)
    preparation, session = await prepared_session(store, owner.id)
    asked = question()
    await store.add_question(owner.id, session.id, asked)
    await store.record_answer(owner.id, session.id, asked.id, answer())
    await store.record_evaluation(owner.id, session.id, asked.id, evaluation(asked.id))

    await store.delete_user(owner.id)

    assert await store.get_user_by_token_hash("token-a") is None
    assert await store.get_preparation(owner.id, preparation.id) is None
    assert await store.get_session(owner.id, session.id) is None
    assert await store.list_awaiting_grade() == ()


@pytest.mark.anyio
async def test_purge_removes_only_users_inactive_before_the_cutoff(store, clock):
    """A retention purge deletes inactive users and leaves active ones."""
    old = await user(store, "old")
    clock.advance(days=2)
    new = await user(store, "new")
    cutoff = clock.current - timedelta(days=1)

    deleted = await store.purge_users(cutoff)

    assert deleted == 1
    assert await store.get_user_by_token_hash("old") is None
    assert await store.get_user_by_token_hash("new") is not None
    assert new.last_seen_at >= cutoff
    assert old.last_seen_at < cutoff
