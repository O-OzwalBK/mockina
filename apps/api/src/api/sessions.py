"""Routes for interview sessions: start one, read it, and end it."""

from uuid import UUID

from contracts import InterviewSession
from fastapi import APIRouter, status

from api.auth import CurrentUser
from api.dependencies import StoreDep
from api.errors import error_responses, require_found
from api.product_models import SessionList, SessionSummary

router = APIRouter(tags=["sessions"])


@router.post(
    "/v1/preparations/{preparation_id}/sessions",
    status_code=status.HTTP_201_CREATED,
    summary="Start Session",
    response_description="A new in-progress session with no questions yet.",
    response_model=InterviewSession,
    responses=error_responses(401, 404, 422),
)
async def start_session(
    preparation_id: UUID, user: CurrentUser, store: StoreDep
) -> InterviewSession:
    """Start a practice session for a preparation, without asking the first question.

    Starting the first session locks the preparation, so its job text can no longer be edited.
    """
    return await store.create_session(user.id, preparation_id)


@router.get(
    "/v1/preparations/{preparation_id}/sessions",
    summary="List Sessions",
    response_description="The preparation's sessions, newest first.",
    response_model=SessionList,
    responses=error_responses(401, 404, 422),
)
async def list_sessions(preparation_id: UUID, user: CurrentUser, store: StoreDep) -> SessionList:
    """List a preparation's sessions with how many questions each holds and has graded."""
    records = await store.list_sessions(user.id, preparation_id)
    return SessionList(items=[SessionSummary.model_validate(record) for record in records])


@router.get(
    "/v1/sessions/{session_id}",
    summary="Read Session",
    response_description="The session with every turn, answer and evaluation.",
    response_model=InterviewSession,
    responses=error_responses(401, 404, 422),
)
async def read_session(session_id: UUID, user: CurrentUser, store: StoreDep) -> InterviewSession:
    """Read one session in full. Another user's session is reported as not found."""
    return require_found(await store.get_session(user.id, session_id))


@router.post(
    "/v1/sessions/{session_id}/complete",
    summary="Complete Session",
    response_description="The session summary after completion.",
    response_model=SessionSummary,
    responses=error_responses(401, 404, 409, 422),
)
async def complete_session(session_id: UUID, user: CurrentUser, store: StoreDep) -> SessionSummary:
    """End a session as completed.

    A question that is still waiting for its answer is dropped. A session needs at least one
    answered question, otherwise this answers 409 `invalid_state`. Completing a completed
    session again returns the same summary. Answers that are still being graded keep being
    graded.
    """
    return SessionSummary.model_validate(await store.complete_session(user.id, session_id))


@router.post(
    "/v1/sessions/{session_id}/abandon",
    summary="Abandon Session",
    response_description="The session summary after abandoning.",
    response_model=SessionSummary,
    responses=error_responses(401, 404, 409, 422),
)
async def abandon_session(session_id: UUID, user: CurrentUser, store: StoreDep) -> SessionSummary:
    """End a session without finishing it. No answer is needed.

    Abandoning an abandoned session again returns the same summary; a completed session cannot
    be abandoned (409 `invalid_state`). Answers already being graded keep being graded.
    """
    return SessionSummary.model_validate(await store.abandon_session(user.id, session_id))
