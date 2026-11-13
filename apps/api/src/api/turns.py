"""Routes for the turns of a session: asking the next question."""

import asyncio
from uuid import UUID

from contracts import Question, SessionStatus, Turn
from contracts.session import MAX_TURNS_PER_SESSION
from engine import InterviewFinished
from fastapi import APIRouter, Response, status
from session_store import OpenQuestionError, SessionStore

from api.auth import CurrentUser
from api.dependencies import InterviewerDep, SessionLocksDep, SettingsDep, StoreDep
from api.errors import ApiError, error_responses, require_found

router = APIRouter(tags=["turns"])


async def questions_from_other_sessions(
    store: SessionStore, user_id: UUID, preparation_id: UUID, own_question_ids: set[UUID]
) -> list[Question]:
    """The preparation's earlier questions, without the ones asked in the current session.

    The store returns every question of every session of the preparation, including this
    session's own. The engine receives this session's turns separately, so counting them again
    here would make it think they were asked twice.
    """
    everything = await store.questions_asked(user_id, preparation_id)
    return [question for question in everything if question.id not in own_question_ids]


@router.post(
    "/v1/sessions/{session_id}/turns",
    status_code=status.HTTP_201_CREATED,
    summary="Ask Next Question",
    response_description="The new question, waiting for its answer.",
    response_model=Turn,
    responses={
        200: {
            "model": Turn,
            "description": "A question was already waiting for its answer; here it is again.",
        },
        **error_responses(401, 404, 409, 413, 422, 502, 503, 504),
    },
)
async def ask_next_question(
    session_id: UUID,
    response: Response,
    user: CurrentUser,
    store: StoreDep,
    interviewer: InterviewerDep,
    locks: SessionLocksDep,
    settings: SettingsDep,
) -> Turn:
    """Ask the next question of a session.

    Safe to repeat. If a question is already waiting for its answer, that same question comes
    back with status 200 and the model is not asked again. Otherwise a new question is written
    and stored, and the answer is 201. The first question of a preparation also extracts the
    skills from its job description, so it takes longer.

    Errors: 409 `session_finished` when the interview has no more questions (the end rule was
    reached, or the session holds 100 questions); 409 `invalid_state` when the session is
    completed or abandoned; 504 `llm_timeout` when the question takes longer than the server's
    deadline, which is safe to retry.
    """
    async with locks.hold(session_id):
        session = require_found(await store.get_session(user.id, session_id))
        if session.status != SessionStatus.IN_PROGRESS:
            raise ApiError(409, "invalid_state", "The session is not in progress.")

        open_turn = await store.get_open_turn(user.id, session_id)
        if open_turn is not None:
            response.status_code = status.HTTP_200_OK
            return open_turn

        if len(session.turns) >= MAX_TURNS_PER_SESSION:
            raise ApiError(
                409,
                "session_finished",
                "The session already holds the maximum number of questions.",
                details={"reason": "question_count_reached"},
            )

        preparation = require_found(await store.get_preparation(user.id, session.preparation_id))
        earlier = await questions_from_other_sessions(
            store, user.id, preparation.id, {turn.question.id for turn in session.turns}
        )

        try:
            async with asyncio.timeout(settings.turn_timeout_seconds):
                outcome = await interviewer.next_question(
                    user_id=user.id,
                    preparation=preparation,
                    turns=session.turns,
                    earlier_questions=earlier,
                )
        except TimeoutError:
            raise ApiError(
                504,
                "llm_timeout",
                "The next question took too long to prepare. Try again.",
                retryable=True,
            ) from None

        if isinstance(outcome, InterviewFinished):
            raise ApiError(
                409,
                "session_finished",
                "The interview has no more questions.",
                details={"reason": outcome.reason.value},
            )

        try:
            return await store.add_question(user.id, session_id, outcome)
        except OpenQuestionError as conflict:
            # Another server process asked at the same moment and won: hand back its question.
            response.status_code = status.HTTP_200_OK
            return conflict.turn