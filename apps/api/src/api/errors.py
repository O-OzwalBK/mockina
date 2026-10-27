"""One error type for product failures, and the mapping from store errors to HTTP answers.

Every failure the API reports uses the same JSON envelope:
``{"error": {"code", "message", "retryable", "details"}}``. Routes raise `ApiError`
for failures they decide on themselves (for example ``unauthorized``). Failures that
come from the session store are raised as store errors and mapped here, so a route
never needs to catch them just to pick a status code.

Messages in this module are fixed sentences. They never include text from the error
being mapped, because store errors can sit next to job text, answers or tokens.
"""

import logging
from collections.abc import Mapping
from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse
from session_store import (
    InvalidStateError,
    NotFoundError,
    OpenQuestionError,
    PreparationLockedError,
    SessionFullError,
    SessionStoreError,
)

from api.models import ErrorResponse

logger = logging.getLogger(__name__)

ERROR_DESCRIPTIONS: dict[int, str] = {
    401: "A valid bearer token is required.",
    404: "The item does not exist, or belongs to somebody else.",
    409: "The request conflicts with the current state of the item.",
    422: "The request body or parameters are invalid.",
    502: "The upstream model request failed.",
    504: "The upstream model timed out.",
}


def error_responses(*statuses: int) -> dict[int | str, dict[str, Any]]:
    """OpenAPI ``responses`` entries that document the shared error envelope for these statuses."""
    return {
        status_code: {"model": ErrorResponse, "description": ERROR_DESCRIPTIONS[status_code]}
        for status_code in statuses
    }


class ApiError(Exception):
    """A failure that the API reports with its own status, stable code and safe message."""

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        *,
        retryable: bool = False,
        details: dict[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> None:
        """Describe the answer: HTTP status, machine code, safe message and optional extras."""
        super().__init__(message)
        self.status_code = status_code
        """HTTP status of the answer."""
        self.code = code
        """Stable machine-readable identifier, for example ``unauthorized``."""
        self.message = message
        """Developer-oriented sentence with no job text, answer, prompt or token in it."""
        self.retryable = retryable
        """Whether sending the same request again may succeed."""
        self.details = details if details is not None else {}
        """Structured, error-specific information."""
        self.headers = dict(headers) if headers is not None else None
        """Extra response headers, for example ``WWW-Authenticate``."""


def error_response(error: ApiError) -> JSONResponse:
    """Turn an ApiError into the shared JSON envelope."""
    return JSONResponse(
        status_code=error.status_code,
        headers=error.headers,
        content={
            "error": {
                "code": error.code,
                "message": error.message,
                "retryable": error.retryable,
                "details": error.details,
            }
        },
    )


async def api_error_handler(_: Request, error: ApiError) -> JSONResponse:
    """Exception handler for ApiError."""
    return error_response(error)


# Looked up by exact class, like LLM_ERROR_MAP: (status, code, fixed message).
STORE_ERROR_MAP: dict[type[SessionStoreError], tuple[int, str, str]] = {
    NotFoundError: (404, "not_found", "The requested item was not found."),
    PreparationLockedError: (
        409,
        "preparation_locked",
        "The preparation already has a session, so it can no longer be edited.",
    ),
    InvalidStateError: (
        409,
        "invalid_state",
        "The session or question is not in the state this action needs.",
    ),
    SessionFullError: (
        409,
        "session_finished",
        "The session already holds the maximum number of questions.",
    ),
    OpenQuestionError: (
        409,
        "invalid_state",
        "The session already has a question waiting for an answer.",
    ),
}


async def store_error_handler(_: Request, error: SessionStoreError) -> JSONResponse:
    """Exception handler for the session store's errors.

    A store error nobody mapped is a bug, so it becomes the generic internal error and
    only its class name is logged.
    """
    mapping = STORE_ERROR_MAP.get(type(error))
    if mapping is None:
        logger.error("Unmapped store error (%s)", type(error).__name__)
        return error_response(
            ApiError(500, "internal_error", "An unexpected server error occurred.")
        )

    status_code, code, message = mapping
    return error_response(ApiError(status_code, code, message))
