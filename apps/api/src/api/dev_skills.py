"""Developer-only routes for trying skill extraction against the configured model."""

import logging
from time import perf_counter
from typing import Annotated, Any

from contracts.preparation import MAX_JOB_DESCRIPTION_LENGTH, MAX_JOB_TITLE_LENGTH
from fastapi import APIRouter, Body, Depends, Query, Request
from fastapi.exceptions import RequestValidationError
from llm_gateway import LLM
from skill_graph import SkillCatalog, extract_skills

from api.dependencies import get_llm, get_skill_catalog
from api.model_calls import LoggedLLM
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


def _blank_field(location: tuple[str, ...], name: str) -> RequestValidationError:
    """Build the shared 422 for a field that became empty after trimming."""
    return RequestValidationError(
        [
            {
                "type": "string_too_short",
                "loc": (*location, name),
                "msg": "String should have at least 1 character",
                "input": "",
            }
        ]
    )


async def _extraction_response(
    *,
    job_title: str,
    job_description: str,
    request: Request,
    llm: LLM,
    catalog: SkillCatalog,
) -> SkillExtractionResponse:
    """Run skill extraction once and wrap the graph with its elapsed time."""
    started = perf_counter()
    settings = getattr(request.app.state, "llm_settings", None)
    model_name = getattr(settings, "model", "injected")
    graph = await extract_skills(
        LoggedLLM(llm, model_name=model_name, logger=logger),
        catalog,
        job_title=job_title,
        job_description=job_description,
    )
    return SkillExtractionResponse(
        graph=graph,
        elapsed_ms=int((perf_counter() - started) * 1000),
    )


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
    return await _extraction_response(
        job_title=request_body.job_title,
        job_description=request_body.job_description,
        request=request,
        llm=llm,
        catalog=catalog,
    )


@router.post(
    "/v1/dev/extract-skills/raw",
    summary="Extract a job's technical skill graph from plain text",
    response_description="The validated skill graph and extraction time.",
    response_model=SkillExtractionResponse,
    responses=ERROR_RESPONSES,
)
async def extract_job_skills_raw(
    request: Request,
    job_title: Annotated[str, Query(min_length=1, max_length=MAX_JOB_TITLE_LENGTH)],
    job_description: Annotated[
        str,
        Body(
            media_type="text/plain",
            min_length=1,
            max_length=MAX_JOB_DESCRIPTION_LENGTH,
        ),
    ],
    llm: LLM = Depends(get_llm),
    catalog: SkillCatalog = Depends(get_skill_catalog),
) -> SkillExtractionResponse:
    """Extract skills from a pasted description, so line breaks need no JSON escaping.

    The body is the job description as text. The title is a query parameter. Limits
    and the response are the same as the JSON route.
    """
    title = job_title.strip()
    if not title:
        raise _blank_field(("query",), "job_title")
    description = job_description.strip()
    if not description:
        raise _blank_field(("body",), "job_description")
    return await _extraction_response(
        job_title=title,
        job_description=description,
        request=request,
        llm=llm,
        catalog=catalog,
    )
