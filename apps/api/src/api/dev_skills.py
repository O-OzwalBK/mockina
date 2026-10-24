"""Developer-only route for trying skill extraction against the configured model."""

import logging
from collections.abc import Sequence
from time import perf_counter
from typing import Any

from fastapi import APIRouter, Depends, Request
from llm_gateway import LLM, LLMError
from llm_gateway.models import ChatMessage, Completion
from skill_graph import SkillCatalog, extract_skills

from api.dependencies import get_llm, get_skill_catalog
from api.models import ErrorResponse, SkillExtractionRequest, SkillExtractionResponse

logger = logging.getLogger(__name__)
router = APIRouter()
ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    413: {"model": ErrorResponse, "description": "The model context budget was exceeded."},
    422: {"model": ErrorResponse, "description": "The request body is invalid."},
    500: {"model": ErrorResponse, "description": "An unexpected API error occurred."},
    502: {"model": ErrorResponse, "description": "Skill extraction or the upstream model failed."},
    503: {"model": ErrorResponse, "description": "The upstream model is rate limited."},
    504: {"model": ErrorResponse, "description": "The upstream model timed out."},
}


class _LoggedLLM:
    """Record safe metadata for each model request made during one extraction."""

    def __init__(self, llm: LLM, *, model_name: str) -> None:
        self._llm = llm
        self._model_name = model_name

    async def complete(
        self,
        messages: Sequence[ChatMessage],
        *,
        temperature: float = 0.2,
        max_output_tokens: int | None = None,
    ) -> Completion:
        """Forward one model call and log only its outcome and usage metadata."""
        started = perf_counter()
        try:
            completion = await self._llm.complete(
                messages,
                temperature=temperature,
                max_output_tokens=max_output_tokens,
            )
        except LLMError as error:
            elapsed_ms = int((perf_counter() - started) * 1000)
            logger.info(
                "model_call outcome=%s model=%s elapsed_ms=%d "
                "prompt_tokens=unknown completion_tokens=unknown",
                type(error).__name__,
                self._model_name,
                elapsed_ms,
            )
            raise

        elapsed_ms = int((perf_counter() - started) * 1000)
        logger.info(
            "model_call outcome=ok model=%s elapsed_ms=%d prompt_tokens=%s completion_tokens=%s",
            completion.model,
            elapsed_ms,
            completion.prompt_tokens,
            completion.completion_tokens,
        )
        return completion


@router.post(
    "/v1/dev/extract-skills",
    summary="Extract a job's technical skill graph",
    response_description="The validated skill graph and extraction time.",
    response_model=SkillExtractionResponse,
    responses=ERROR_RESPONSES,
)
async def extract_job_skills(
    request_body: SkillExtractionRequest,
    request: Request,
    llm: LLM = Depends(get_llm),
    catalog: SkillCatalog = Depends(get_skill_catalog),
) -> SkillExtractionResponse:
    """Extract technical skills from the job title and description, without using a resume."""
    started = perf_counter()
    settings = getattr(request.app.state, "llm_settings", None)
    model_name = getattr(settings, "model", "injected")
    graph = await extract_skills(
        _LoggedLLM(llm, model_name=model_name),
        catalog,
        job_title=request_body.job_title,
        job_description=request_body.job_description,
    )
    return SkillExtractionResponse(
        graph=graph,
        elapsed_ms=int((perf_counter() - started) * 1000),
    )
