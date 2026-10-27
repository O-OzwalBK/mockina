import logging
import math
import traceback
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from http import HTTPStatus
from time import perf_counter
from typing import Any
from urllib.parse import urlparse

from engine import UnusableQuestionError
from evaluator import EvaluationError
from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from llm_gateway import (
    LLM,
    ContextBudgetExceededError,
    LLMAuthError,
    LLMConnectionError,
    LLMError,
    LLMRateLimitError,
    LLMRequestError,
    LLMResponseError,
    LLMServerError,
    LLMSettings,
    LLMTimeoutError,
    OpenAICompatibleLLM,
    RetryingLLM,
)
from pydantic import ValidationError
from session_store import (
    SessionStore,
    SessionStoreError,
    SessionStoreSettings,
    SQLiteSessionStore,
)
from skill_graph import InMemorySkillStore, SkillGraphError, SkillStore
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.cors import CORSMiddleware

from api.dependencies import get_llm
from api.dev_engine import router as dev_engine_router
from api.dev_evaluator import router as dev_evaluator_router
from api.dev_skills import router as dev_skills_router
from api.errors import ApiError, api_error_handler, store_error_handler
from api.models import CompletionRequest, CompletionResponse, ErrorResponse, ModelInfoResponse
from api.settings import ApiSettings

logger = logging.getLogger(__name__)
LLM_ERROR_MAP: dict[type[LLMError], tuple[int, str]] = {
    ContextBudgetExceededError: (413, "context_too_large"),
    LLMRateLimitError: (503, "llm_rate_limited"),
    LLMTimeoutError: (504, "llm_timeout"),
    LLMConnectionError: (502, "llm_unreachable"),
    LLMServerError: (502, "llm_server_error"),
    LLMResponseError: (502, "llm_bad_response"),
    UnusableQuestionError: (502, "llm_bad_response"),
    EvaluationError: (502, "llm_bad_response"),
    LLMAuthError: (502, "llm_auth_failed"),
    LLMRequestError: (502, "llm_rejected_request"),
}

ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    413: {"model": ErrorResponse, "description": "The model context budget was exceeded."},
    422: {"model": ErrorResponse, "description": "The request body is invalid."},
    500: {"model": ErrorResponse, "description": "An unexpected API error occurred."},
    502: {"model": ErrorResponse, "description": "The upstream model request failed."},
    503: {"model": ErrorResponse, "description": "The upstream model is rate limited."},
    504: {"model": ErrorResponse, "description": "The upstream model timed out."},
}


def describe_settings_problem(error: ValidationError) -> str:
    """List invalid LLM setting names and rules without repeating their values."""

    lines = ["The model settings are not usable, so the API cannot start:"]

    for problem in error.errors():
        location = problem["loc"]
        name = f"LLM_{location[0]}".upper() if location else "LLM settings"
        message = problem["msg"].removeprefix("Value error, ")
        lines.append(f"  {name}: {message}")

    lines.append("Set them in the environment or in .env (see .env.example).")
    return "\n".join(lines)


def create_app(
    settings: ApiSettings | None = None,
    llm: LLM | None = None,
    skill_store: SkillStore | None = None,
    store: SessionStore | None = None,
) -> FastAPI:
    """Build the API with configurable browser settings and optional test doubles.

    `settings` holds the API's own options (CORS origins, dev routes). When it is None they are
    read from the environment and .env, even if `llm` is given, so tests pass `settings`.
    `llm` replaces the real model: when it is given, the model settings (LLM_*) are not read
    at all and no network client is built. `skill_store` replaces the in-memory catalog.
    `store` replaces the durable session store. Without it, startup opens the SQLite file at
    SESSION_STORE_PATH (creating its folder) and shutdown closes it; a store passed in here
    is never closed by the API, because its creator owns it.
    """

    api_settings = settings if settings is not None else ApiSettings()

    @asynccontextmanager
    async def serve_model(application: FastAPI) -> AsyncGenerator[None, None]:
        """Put the model on app.state: the injected one, or a real client closed afterwards."""
        if llm is not None:
            application.state.llm = llm
            yield
            return

        try:
            # pydantic-settings loads the required values from the environment or .env file.
            llm_settings = LLMSettings()  # pyright: ignore[reportCallIssue]
        except ValidationError as error:
            message = describe_settings_problem(error)
            logger.critical(message)
            raise RuntimeError(message) from None

        client = OpenAICompatibleLLM(llm_settings)
        application.state.llm_settings = llm_settings
        application.state.llm = RetryingLLM(client, max_retries=llm_settings.max_retries)
        try:
            yield
        finally:
            await client.aclose()

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncGenerator[None, None]:
        application.state.skill_store = (
            skill_store if skill_store is not None else InMemorySkillStore()
        )
        opened_store: SQLiteSessionStore | None = None
        if store is not None:
            application.state.store = store
        else:
            database_path = SessionStoreSettings().path
            database_path.parent.mkdir(parents=True, exist_ok=True)
            opened_store = SQLiteSessionStore(database_path)
            application.state.store = opened_store

        try:
            async with serve_model(application):
                yield
        finally:
            if opened_store is not None:
                opened_store.close()

    app = FastAPI(
        title="Mockina API",
        description="Backend for the Mockina AI mock-interview platform.",
        version="0.1.0",
        lifespan=lifespan,
    )

    @app.middleware("http")
    async def unexpected_error_middleware(request: Request, call_next):
        try:
            return await call_next(request)
        except Exception as error:
            stack = "".join(traceback.format_tb(error.__traceback__))
            logger.error("Unhandled API exception (%s)\n%s", type(error).__name__, stack)
            return JSONResponse(
                status_code=500,
                content={
                    "error": {
                        "code": "internal_error",
                        "message": "An unexpected server error occurred.",
                        "retryable": False,
                        "details": {},
                    }
                },
            )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(api_settings.cors_origins),
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
        allow_credentials=False,
    )

    @app.get(
        "/health",
        summary="Check API health",
        response_description="The API is running.",
    )
    def health() -> dict[str, str]:
        """Report that the API is reachable without calling the model."""
        return {"status": "healthy"}

    app.exception_handler(ApiError)(api_error_handler)
    app.exception_handler(SessionStoreError)(store_error_handler)

    @app.exception_handler(LLMError)
    async def llm_error_handler(_: Request, error: LLMError) -> JSONResponse:
        mapping = LLM_ERROR_MAP.get(type(error))
        if mapping is None:
            status_code, code = 500, "internal_error"
            message = "An unexpected model error occurred."
        else:
            status_code, code = mapping
            message = str(error)

        details: dict[str, object] = {}
        if isinstance(error, ContextBudgetExceededError):
            if error.estimated_tokens is not None:
                details["estimated_tokens"] = error.estimated_tokens
            if error.budget_tokens is not None:
                details["budget_tokens"] = error.budget_tokens
        headers = None
        if isinstance(error, LLMRateLimitError) and error.retry_after is not None:
            headers = {"Retry-After": str(math.ceil(error.retry_after))}

        return JSONResponse(
            status_code=status_code,
            headers=headers,
            content={
                "error": {
                    "code": code,
                    "message": message,
                    "retryable": error.retryable,
                    "details": details,
                }
            },
        )

    @app.exception_handler(SkillGraphError)
    async def skill_graph_error_handler(_: Request, error: SkillGraphError) -> JSONResponse:
        logger.warning(
            "skill_graph_error type=%s reason=%s",
            type(error).__name__,
            getattr(error, "reason", "invalid_graph"),
        )
        return JSONResponse(
            status_code=502,
            content={
                "error": {
                    "code": "llm_bad_response",
                    "message": "The model could not produce a valid skill graph.",
                    "retryable": False,
                    "details": {},
                }
            },
        )

    @app.exception_handler(RequestValidationError)
    async def request_validation_error_handler(
        _: Request, error: RequestValidationError
    ) -> JSONResponse:
        validation_errors = [
            {"loc": item["loc"], "msg": item["msg"], "type": item["type"]}
            for item in error.errors()
        ]
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "invalid_request",
                    "message": "The request body is invalid.",
                    "retryable": False,
                    "details": {"errors": validation_errors},
                }
            },
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(_: Request, error: StarletteHTTPException) -> JSONResponse:

        codes = {
            404: "not_found",
            405: "method_not_allowed",
        }
        code = codes.get(error.status_code, "http_error")

        try:
            message = HTTPStatus(error.status_code).phrase
        except ValueError:
            message = "HTTP error"

        return JSONResponse(
            status_code=error.status_code,
            headers=error.headers,
            content={
                "error": {
                    "code": code,
                    "message": message,
                    "retryable": False,
                    "details": {},
                }
            },
        )

    if api_settings.dev_routes:
        app.include_router(dev_skills_router)
        app.include_router(dev_engine_router)
        app.include_router(dev_evaluator_router)

        @app.post(
            "/v1/dev/complete",
            summary="Complete a model conversation",
            response_description="The model reply and provider-reported usage.",
            response_model=CompletionResponse,
            responses=ERROR_RESPONSES,
        )
        async def complete(
            request_body: CompletionRequest,
            request: Request,
            llm: LLM = Depends(get_llm),
        ) -> CompletionResponse:
            """Pass the supplied messages to the configured model and return its reply."""
            started = perf_counter()
            llm_settings = getattr(request.app.state, "llm_settings", None)
            configured_model = getattr(llm_settings, "model", "injected")
            try:
                completion = await llm.complete(
                    request_body.messages,
                    temperature=request_body.temperature,
                    max_output_tokens=request_body.max_output_tokens,
                )
            except LLMError as error:
                elapsed_ms = int((perf_counter() - started) * 1000)
                logger.info(
                    "model_call outcome=%s model=%s elapsed_ms=%d "
                    "prompt_tokens=unknown completion_tokens=unknown",
                    type(error).__name__,
                    configured_model,
                    elapsed_ms,
                )
                raise
            except Exception as error:
                elapsed_ms = int((perf_counter() - started) * 1000)
                logger.info(
                    "model_call outcome=%s model=%s elapsed_ms=%d "
                    "prompt_tokens=unknown completion_tokens=unknown",
                    type(error).__name__,
                    configured_model,
                    elapsed_ms,
                )
                raise

            elapsed_ms = int((perf_counter() - started) * 1000)
            logger.info(
                "model_call outcome=ok model=%s elapsed_ms=%d prompt_tokens=%s "
                "completion_tokens=%s",
                completion.model,
                elapsed_ms,
                completion.prompt_tokens,
                completion.completion_tokens,
            )
            return CompletionResponse(
                text=completion.text,
                model=completion.model,
                finish_reason=completion.finish_reason,
                prompt_tokens=completion.prompt_tokens,
                completion_tokens=completion.completion_tokens,
                elapsed_ms=elapsed_ms,
            )

        @app.get(
            "/v1/dev/model",
            summary="Show configured model details",
            response_description="Non-secret details about the configured model endpoint.",
            response_model=ModelInfoResponse,
            responses={
                503: {
                    "model": ErrorResponse,
                    "description": "No model settings are available: a test model was injected.",
                }
            },
        )
        def model_info(request: Request) -> ModelInfoResponse | JSONResponse:
            """Return model limits and provider host without exposing the API key."""
            llm_settings = getattr(request.app.state, "llm_settings", None)
            if llm_settings is None:
                return JSONResponse(
                    status_code=503,
                    content={
                        "error": {
                            "code": "model_not_configured",
                            "message": "Model settings are unavailable for an injected model.",
                            "retryable": False,
                            "details": {},
                        }
                    },
                )
            return ModelInfoResponse(
                model=llm_settings.model,
                host=urlparse(llm_settings.base_url).netloc.rsplit("@", maxsplit=1)[-1],
                context_tokens=llm_settings.context_tokens,
                max_output_tokens=llm_settings.max_output_tokens,
                api_key_set=llm_settings.api_key is not None,
            )

    return app


app = create_app()
