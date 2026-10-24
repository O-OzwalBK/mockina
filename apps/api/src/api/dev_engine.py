"""Developer-only route for trying the interview engine against the configured model."""

import logging
from time import perf_counter
from typing import Any

from contracts import Preparation
from engine import InterviewFinished, next_turn
from fastapi import APIRouter, Depends, Request
from llm_gateway import LLM

from api.dependencies import get_llm
from api.model_calls import LoggedLLM
from api.models import ErrorResponse, NextTurnRequest, NextTurnResponse

logger = logging.getLogger(__name__)
router = APIRouter()
ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    413: {"model": ErrorResponse, "description": "The model context budget was exceeded."},
    422: {"model": ErrorResponse, "description": "The request body is invalid."},
    500: {"model": ErrorResponse, "description": "An unexpected API error occurred."},
    502: {"model": ErrorResponse, "description": "The engine or the upstream model failed."},
    503: {"model": ErrorResponse, "description": "The upstream model is rate limited."},
    504: {"model": ErrorResponse, "description": "The upstream model timed out."},
}


@router.post(
    "/v1/dev/next-question",
    summary="Ask the engine for the next question",
    response_description="The next question or the finished reason, with elapsed time.",
    response_model=NextTurnResponse,
    responses=ERROR_RESPONSES,
)
async def next_question(
    request_body: NextTurnRequest,
    request: Request,
    llm: LLM = Depends(get_llm),
) -> NextTurnResponse:
    """Run one engine turn with the supplied session and store nothing."""
    started = perf_counter()
    settings = getattr(request.app.state, "llm_settings", None)
    model_name = getattr(settings, "model", "injected")
    preparation = Preparation(
        job_title=request_body.job_title,
        job_description=request_body.job_description,
        resume=request_body.resume,
    )
    outcome = await next_turn(
        preparation,
        request_body.skill_graph,
        request_body.turns,
        request_body.earlier_questions,
        request_body.interview_config,
        LoggedLLM(llm, model_name=model_name, logger=logger),
    )
    elapsed_ms = int((perf_counter() - started) * 1000)

    if isinstance(outcome, InterviewFinished):
        logger.info(
            "dev_engine outcome=finished reason=%s elapsed_ms=%d", outcome.reason, elapsed_ms
        )
        return NextTurnResponse(finished=outcome, elapsed_ms=elapsed_ms)
    logger.info("dev_engine outcome=question elapsed_ms=%d", elapsed_ms)
    return NextTurnResponse(question=outcome, elapsed_ms=elapsed_ms)
