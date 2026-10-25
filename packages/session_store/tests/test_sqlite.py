import pytest
from contracts import Answer, PreparationCreate, Question, SkillGraph, SkillNode, skill_id
from session_store import SQLiteSessionStore


def _preparation() -> PreparationCreate:
    """A preparation with a marker in the resume for the deletion test."""
    return PreparationCreate(
        job_title="Backend Engineer",
        job_description="Build backend services.",
        resume="A private resume marker.",
    )


def _graph() -> SkillGraph:
    """A small valid graph for the durability test."""
    root = SkillNode(id=skill_id("Backend", "Backend"), label="Backend", parent_id=None)
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


@pytest.mark.anyio
async def test_sqlite_data_survives_close_and_reopen(tmp_path, clock):
    """Closing the store and opening the same file keeps the user and session."""
    path = tmp_path / "session-store.db"
    first = SQLiteSessionStore(path, clock=clock)
    owner = await first.create_user("hash")
    preparation = await first.create_preparation(owner.id, _preparation())
    await first.save_skill_graph_if_absent(owner.id, preparation.id, _graph())
    session = await first.create_session(owner.id, preparation.id)
    asked = Question(text="What is a closure?", skill_id="javascript", difficulty=2)
    await first.add_question(owner.id, session.id, asked)
    await first.record_answer(
        owner.id,
        session.id,
        asked.id,
        Answer(transcript="A function with its scope.", duration=12.0),
    )
    first.close()

    second = SQLiteSessionStore(path, clock=clock)
    try:
        assert (await second.get_user_by_token_hash("hash")) is not None
        assert await second.get_preparation(owner.id, preparation.id) == preparation
        assert await second.get_skill_graph(owner.id, preparation.id) == _graph()
        saved = await second.get_session(owner.id, session.id)
        assert saved is not None
        assert saved.turns[0].answer is not None
        assert saved.turns[0].answer.transcript == "A function with its scope."
    finally:
        second.close()


@pytest.mark.anyio
async def test_delete_user_removes_the_answer_from_the_database_and_wal(tmp_path, clock):
    """Secure delete plus a WAL checkpoint leaves no deleted answer text in the files."""
    path = tmp_path / "session-store.db"
    marker = "SECRET-ANSWER-MARKER-9f7c1a"
    store = SQLiteSessionStore(path, clock=clock)
    owner = await store.create_user("hash")
    preparation = await store.create_preparation(owner.id, _preparation())
    session = await store.create_session(owner.id, preparation.id)
    asked = Question(text="What is a closure?", skill_id="javascript", difficulty=2)
    await store.add_question(owner.id, session.id, asked)
    await store.record_answer(
        owner.id,
        session.id,
        asked.id,
        Answer(transcript=marker, duration=12.0),
    )

    await store.delete_user(owner.id)
    store.close()

    for candidate in (path, path.with_name(path.name + "-wal")):
        if candidate.exists():
            assert marker.encode() not in candidate.read_bytes()
