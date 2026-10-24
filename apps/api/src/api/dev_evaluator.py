"""Developer-only route for trying the evaluator against the configured model."""

import logging
from collections.abc import Sequence
from time import perf_counter
from typing import Any

from evaluator import grade_answer
from fastapi import APIRouter, Depends, Request
from llm_gateway import LLM, ChatMessage, Completion

from api.dependencies import get_llm
from api.model_calls import LoggedLLM
from api.models import ErrorResponse, GradeRequest, GradeResponse

logger = logging.getLogger(__name__)
router = APIRouter()
ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    413: {"model": ErrorResponse, "description": "The model context budget was exceeded."},
    422: {"model": ErrorResponse, "description": "The request body is invalid."},
    500: {"model": ErrorResponse, "description": "An unexpected API error occurred."},
    502: {"model": ErrorResponse, "description": "The evaluator or the upstream model failed."},
    503: {"model": ErrorResponse, "description": "The upstream model is rate limited."},
    504: {"model": ErrorResponse, "description": "The upstream model timed out."},
}


class _RecordingLLM:
    """Record the last grading call's provider token counts for the response."""

    def __init__(self, llm: LLM) -> None:
        """Wrap one model for one developer grading request."""
        self._llm = llm
        self.prompt_tokens: int | None = None
        self.completion_tokens: int | None = None

    async def complete(
        self,
        messages: Sequence[ChatMessage],
        *,
        temperature: float = 0.2,
        max_output_tokens: int | None = None,
    ) -> Completion:
        """Forward one grading call and keep its usage metadata."""
        completion = await self._llm.complete(
            messages,
            temperature=temperature,
            max_output_tokens=max_output_tokens,
        )
        self.prompt_tokens = completion.prompt_tokens
        self.completion_tokens = completion.completion_tokens
        return completion


@router.post(
    "/v1/dev/grade",
    summary="Grade one interview answer",
    response_description="The evaluation, the evaluator call duration, and provider token usage.",
    response_model=GradeResponse,
    responses=ERROR_RESPONSES,
)
async def grade_one_answer(
    request_body: GradeRequest,
    request: Request,
    llm: LLM = Depends(get_llm),
) -> GradeResponse:
    """Grade one answer with the supplied question and job title, and store nothing."""
    started = perf_counter()
    settings = getattr(request.app.state, "llm_settings", None)
    model_name = getattr(settings, "model", "injected")
    recorder = _RecordingLLM(LoggedLLM(llm, model_name=model_name, logger=logger))
    evaluation = await grade_answer(
        recorder,
        question=request_body.question,
        answer=request_body.answer,
        job_title=request_body.job_title,
    )
    elapsed_ms = int((perf_counter() - started) * 1000)
    logger.info("dev_grade outcome=ok elapsed_ms=%d", elapsed_ms)
    return GradeResponse(
        evaluation=evaluation,
        elapsed_ms=elapsed_ms,
        prompt_tokens=recorder.prompt_tokens,
        completion_tokens=recorder.completion_tokens,
    )
