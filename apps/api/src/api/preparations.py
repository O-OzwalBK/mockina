"""Routes for preparations: the job a person is getting ready for."""

from uuid import UUID

from contracts import Preparation, PreparationCreate
from fastapi import APIRouter, status

from api.auth import CurrentUser
from api.dependencies import StoreDep
from api.errors import error_responses, require_found
from api.product_models import PreparationList, PreparationSummary, PreparationUpdate

router = APIRouter(prefix="/v1/preparations", tags=["preparations"])


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    summary="Create Preparation",
    response_description="The stored preparation, with its id and creation time.",
    response_model=Preparation,
    responses=error_responses(401, 422),
)
async def create_preparation(
    body: PreparationCreate, user: CurrentUser, store: StoreDep
) -> Preparation:
    """Save a job description (and optionally a resume) to practice for.

    No model call happens here. The skills to ask about are extracted from the job
    description when the first question of the first session is requested.
    """
    return await store.create_preparation(user.id, body)


@router.get(
    "",
    summary="List Preparations",
    response_description="The caller's preparations, newest first.",
    response_model=PreparationList,
    responses=error_responses(401),
)
async def list_preparations(user: CurrentUser, store: StoreDep) -> PreparationList:
    """List the caller's preparations with how many sessions each has."""
    records = await store.list_preparations(user.id)
    return PreparationList(items=[PreparationSummary.model_validate(record) for record in records])


@router.get(
    "/{preparation_id}",
    summary="Read Preparation",
    response_description="The preparation.",
    response_model=Preparation,
    responses=error_responses(401, 404, 422),
)
async def read_preparation(preparation_id: UUID, user: CurrentUser, store: StoreDep) -> Preparation:
    """Read one preparation. Another user's preparation is reported as not found."""
    return require_found(await store.get_preparation(user.id, preparation_id))


@router.patch(
    "/{preparation_id}",
    summary="Update Preparation",
    response_description="The preparation after the change.",
    response_model=Preparation,
    responses=error_responses(401, 404, 409, 422),
)
async def update_preparation(
    preparation_id: UUID, body: PreparationUpdate, user: CurrentUser, store: StoreDep
) -> Preparation:
    """Change some fields of a preparation that has no session yet.

    Fields left out keep their value; `resume: null` removes the resume. Once a session
    exists the preparation is locked and this answers 409 `preparation_locked`. Changing the
    job title or description discards the skills extracted for it, so they are extracted
    again from the new text.
    """
    current = require_found(await store.get_preparation(user.id, preparation_id))
    changes = body.model_dump(exclude_unset=True)
    return await store.update_preparation(
        user.id,
        preparation_id,
        job_title=changes.get("job_title", current.job_title),
        job_description=changes.get("job_description", current.job_description),
        resume=changes["resume"] if "resume" in changes else current.resume,
    )


@router.delete(
    "/{preparation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete Preparation",
    response_description="The preparation and its sessions were deleted.",
    responses=error_responses(401, 404, 422),
)
async def delete_preparation(preparation_id: UUID, user: CurrentUser, store: StoreDep) -> None:
    """Delete a preparation together with its sessions, answers, evaluations and skills."""
    await store.delete_preparation(user.id, preparation_id)
