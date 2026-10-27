"""Routes for the anonymous identity: create one, delete one with all its data."""

from typing import Annotated

from fastapi import APIRouter, Depends, status
from session_store import NotFoundError
from skill_graph import SkillCatalog

from api.auth import CurrentUser, generate_token, hash_token
from api.dependencies import StoreDep, get_skill_catalog
from api.errors import error_responses
from api.product_models import Identity

router = APIRouter(prefix="/v1/identity", tags=["identity"])


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    summary="Create Anonymous Identity",
    response_description="The new identity, including its bearer token, which is shown only once.",
    response_model=Identity,
)
async def create_identity(store: StoreDep) -> Identity:
    """Create an anonymous user and return the secret token that acts as their password.

    No account details are asked for. The token is generated here, returned once, and only
    its hash is stored, so lose it and the data behind it can no longer be reached.
    """
    token = generate_token()
    user = await store.create_user(hash_token(token))
    return Identity(user_id=user.id, token=token, created_at=user.created_at)


@router.delete(
    "",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete Identity And All Data",
    response_description="The identity and everything it owned were deleted.",
    responses=error_responses(401),
)
async def delete_identity(
    user: CurrentUser,
    store: StoreDep,
    catalog: Annotated[SkillCatalog, Depends(get_skill_catalog)],
) -> None:
    """Delete the caller and every preparation, session, answer and evaluation they own.

    Skill labels learned from their job descriptions are forgotten as well. After this the
    token no longer works. Deleting twice at the same moment is harmless.
    """
    # The catalog goes first: if the store then fails, the user still exists and can retry.
    await catalog.forget(str(user.id))
    try:
        await store.delete_user(user.id)
    except NotFoundError:
        pass  # a parallel delete already finished; the user is gone, which is the goal
