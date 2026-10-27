"""Anonymous bearer-token authentication.

A person gets an identity by calling ``POST /v1/identity``. The response holds a random
token that is shown once. The store keeps only the token's SHA-256 hash, so a copy of the
database cannot be used to act as anybody. Each protected route then reads the token from
the ``Authorization: Bearer`` header, hashes it and looks the user up by that hash.

Tokens carry 256 bits of randomness, so a plain fast hash is enough. A slow password hash
would only make every request slower.
"""

import hashlib
import secrets
from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from session_store import NotFoundError, SessionStore, UserRecord

from api.dependencies import get_store
from api.errors import ApiError

TOKEN_BYTES = 32
"""Random bytes in a token: 32 bytes is 256 bits."""

bearer_scheme = HTTPBearer(
    auto_error=False,
    description="Send the token from POST /v1/identity as `Authorization: Bearer <token>`.",
)


def generate_token() -> str:
    """Make a new unguessable token that is safe to put in an HTTP header."""
    return secrets.token_urlsafe(TOKEN_BYTES)


def hash_token(token: str) -> str:
    """Return the SHA-256 hex digest the store keeps instead of the token."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def unauthorized() -> ApiError:
    """The one 401 every authentication failure uses, so callers cannot tell the cases apart."""
    return ApiError(
        401,
        "unauthorized",
        "A valid bearer token is required.",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def require_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    store: Annotated[SessionStore, Depends(get_store)],
) -> UserRecord:
    """Return the user who owns the request's bearer token, or raise the 401 error.

    A missing header, a different scheme, an empty token and an unknown token all produce
    the same answer. A successful call also refreshes the user's last-seen time; the store
    writes that at most once a day.
    """
    if credentials is None or not credentials.credentials:
        raise unauthorized()

    user = await store.get_user_by_token_hash(hash_token(credentials.credentials))
    if user is None:
        raise unauthorized()

    try:
        await store.touch_user(user.id)
    except NotFoundError:
        # The user was deleted between the lookup and the touch.
        raise unauthorized() from None
    return user


CurrentUser = Annotated[UserRecord, Depends(require_user)]
"""Route parameter type: the authenticated user, or a 401 before the route body runs."""
