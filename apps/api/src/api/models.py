from typing import Any

from contracts import InterviewConfig, Question, SkillGraph, Turn
from contracts.preparation import (
    MAX_JOB_DESCRIPTION_LENGTH,
    MAX_JOB_TITLE_LENGTH,
    MAX_RESUME_LENGTH,
)
from contracts.session import MAX_TURNS_PER_SESSION
from engine import InterviewFinished
from llm_gateway import ChatMessage
from pydantic import BaseModel, ConfigDict, Field, model_validator

MAX_MESSAGES = 100
MAX_MESSAGE_CHARS = 20_000
MAX_TOTAL_MESSAGE_CHARS = 100_000
MAX_EARLIER_QUESTIONS = 500


class SkillExtractionRequest(BaseModel):
    """Job information sent to the developer-only skill extraction route."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    job_title: str = Field(
        description="Short title for the target job.",
        min_length=1,
        max_length=MAX_JOB_TITLE_LENGTH,
        examples=["Junior React Developer"],
    )
    job_description: str = Field(
        description="The job description used to identify technical skills.",
        min_length=1,
        max_length=MAX_JOB_DESCRIPTION_LENGTH,
        examples=["Build accessible web interfaces with React and TypeScript."],
    )


class SkillExtractionResponse(BaseModel):
    """Validated skill graph and elapsed time for a developer extraction request."""

    graph: SkillGraph = Field(
        description="The validated category and skill tree for the supplied job.",
        examples=[
            {
                "nodes": [
                    {
                        "id": "cee9c65f-beef-5a90-8f32-34dc4048f4bc",
                        "label": "React",
                        "parent_id": None,
                        "importance": None,
                        "difficulty": None,
                    },
                    {
                        "id": "8dd8e540-014e-52e3-8f87-0fd42abe1678",
                        "label": "Hooks",
                        "parent_id": "cee9c65f-beef-5a90-8f32-34dc4048f4bc",
                        "importance": 4,
                        "difficulty": 3,
                    },
                    {
                        "id": "4ad725ae-ee80-5133-870a-3640ce7418e2",
                        "label": "Effects",
                        "parent_id": "cee9c65f-beef-5a90-8f32-34dc4048f4bc",
                        "importance": 3,
                        "difficulty": 2,
                    },
                    {
                        "id": "eb315a8a-1fb0-5829-b114-f5d805e4c26c",
                        "label": "State",
                        "parent_id": "cee9c65f-beef-5a90-8f32-34dc4048f4bc",
                        "importance": 3,
                        "difficulty": 3,
                    },
                ]
            }
        ],
    )
    elapsed_ms: int = Field(
        description="Elapsed time for skill extraction in milliseconds.",
        ge=0,
        examples=[1200],
    )


class NextTurnRequest(BaseModel):
    """One engine call supplied by a developer; nothing is stored."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    job_title: str = Field(
        description="Short title for the target job.",
        min_length=1,
        max_length=MAX_JOB_TITLE_LENGTH,
        examples=["Junior React Developer"],
    )
    job_description: str = Field(
        description="The job description the question should be about.",
        min_length=1,
        max_length=MAX_JOB_DESCRIPTION_LENGTH,
        examples=["Build accessible interfaces with React and TypeScript."],
    )
    skill_graph: SkillGraph = Field(
        description="The preparation's validated skill tree to ask about.",
        examples=[
            {
                "nodes": [
                    {
                        "id": "cee9c65f-beef-5a90-8f32-34dc4048f4bc",
                        "label": "React",
                        "parent_id": None,
                        "importance": None,
                        "difficulty": None,
                    },
                    {
                        "id": "8dd8e540-014e-52e3-8f87-0fd42abe1678",
                        "label": "Hooks",
                        "parent_id": "cee9c65f-beef-5a90-8f32-34dc4048f4bc",
                        "importance": 4,
                        "difficulty": 3,
                    },
                    {
                        "id": "4ad725ae-ee80-5133-870a-3640ce7418e2",
                        "label": "Effects",
                        "parent_id": "cee9c65f-beef-5a90-8f32-34dc4048f4bc",
                        "importance": 3,
                        "difficulty": 2,
                    },
                    {
                        "id": "eb315a8a-1fb0-5829-b114-f5d805e4c26c",
                        "label": "State",
                        "parent_id": "cee9c65f-beef-5a90-8f32-34dc4048f4bc",
                        "importance": 3,
                        "difficulty": 3,
                    },
                ]
            }
        ],
    )
    interview_config: InterviewConfig = Field(
        description="The resolved end rule for this simulated session.",
        examples=[{"rule": "question_count", "count": 5}],
    )
    resume: str | None = Field(
        default=None,
        description="Optional resume text used only to personalise a question.",
        min_length=1,
        max_length=MAX_RESUME_LENGTH,
        examples=["Built a task tracker with React and TypeScript."],
    )
    turns: list[Turn] = Field(
        default_factory=list,
        max_length=MAX_TURNS_PER_SESSION,
        description="The simulated session's turns so far, in order.",
        examples=[[]],
    )
    earlier_questions: list[Question] = Field(
        default_factory=list,
        max_length=MAX_EARLIER_QUESTIONS,
        description="Questions asked in earlier sessions of the same preparation.",
        examples=[
            [
                {
                    "text": "What is a closure?",
                    "skill_id": "javascript-closures",
                    "difficulty": 2,
                }
            ]
        ],
    )


class NextTurnResponse(BaseModel):
    """The engine's outcome and elapsed time for a developer request."""

    question: Question | None = Field(
        default=None,
        description="The next question, or None when the interview is finished.",
        examples=[
            {
                "text": "How does React batch state updates?",
                "skill_id": "8dd8e540-014e-52e3-8f87-0fd42abe1678",
                "difficulty": 2,
            }
        ],
    )
    finished: InterviewFinished | None = Field(
        default=None,
        description="The finished reason, or None when a question was produced.",
        examples=[{"reason": "question_count_reached"}],
    )
    elapsed_ms: int = Field(
        ge=0,
        description="Elapsed time for the engine call in milliseconds.",
        examples=[900],
    )

    @model_validator(mode="after")
    def check_exactly_one_outcome(self) -> "NextTurnResponse":
        """Exactly one of a question or a finished result is present."""
        if (self.question is None) == (self.finished is None):
            raise ValueError("exactly one of question or finished must be present")
        return self


class CompletionRequest(BaseModel):
    """Caller-provided conversation and generation options for the model."""

    messages: list[ChatMessage] = Field(
        description="Conversation messages passed through to the configured model.",
        examples=[[{"role": "user", "content": "Say hello in one short sentence."}]],
        min_length=1,
        max_length=MAX_MESSAGES,
    )
    temperature: float = Field(
        default=0.2,
        ge=0,
        le=2,
        description="Sampling temperature from 0 (most deterministic) to 2 (most varied).",
        examples=[0.2],
    )
    max_output_tokens: int | None = Field(
        default=None,
        ge=1,
        description="Optional reply limit; when omitted, the configured model default is used.",
        examples=[256],
    )

    @model_validator(mode="after")
    def _message_content_fits_limits(self) -> "CompletionRequest":
        """Bound individual and total message text without including it in errors."""
        if any(len(message.content) > MAX_MESSAGE_CHARS for message in self.messages):
            raise ValueError(f"each message must be at most {MAX_MESSAGE_CHARS} characters")
        total_characters = sum(len(message.content) for message in self.messages)
        if total_characters > MAX_TOTAL_MESSAGE_CHARS:
            raise ValueError(
                f"combined message content must be at most {MAX_TOTAL_MESSAGE_CHARS} characters"
            )
        return self


class CompletionResponse(BaseModel):
    """Model reply and provider-reported usage, with the API call duration."""

    text: str = Field(
        description="The reply text, exactly as the model returned it.",
        examples=["Hello!"],
    )
    model: str = Field(
        description="Model name reported by the provider.",
        examples=["openai/gpt-oss-20b"],
    )
    finish_reason: str | None = Field(
        description="Why generation stopped, when the provider reported a reason.",
        examples=["stop"],
    )
    prompt_tokens: int | None = Field(
        description="Provider-reported prompt token count, when available.",
        examples=[78],
    )
    completion_tokens: int | None = Field(
        description="Provider-reported reply token count, when available.",
        examples=[87],
    )
    elapsed_ms: int = Field(
        ge=0,
        description="Elapsed time for the model call in milliseconds.",
        examples=[600],
    )


class ErrorDetail(BaseModel):
    """Stable error information returned to API callers."""

    code: str = Field(
        description="Stable machine-readable error identifier.",
        examples=["llm_timeout"],
    )
    message: str = Field(
        description="Developer-oriented message that contains no prompt or secret values.",
        examples=["The model server did not answer within the time limit."],
    )
    retryable: bool = Field(
        description="Whether retrying the same request may succeed.",
        examples=[True],
    )
    details: dict[str, Any] = Field(
        description="Structured error-specific information, when available.",
        examples=[{"estimated_tokens": 9000, "budget_tokens": 7168}],
    )


class ErrorResponse(BaseModel):
    """Shared error envelope for API failures."""

    error: ErrorDetail = Field(
        description="The error code, safe message, retryability, and optional details.",
        examples=[
            {
                "code": "llm_timeout",
                "message": "The model server did not answer within the time limit.",
                "retryable": True,
                "details": {},
            }
        ],
    )


class ModelInfoResponse(BaseModel):
    """Non-secret model configuration exposed by the developer model-info route."""

    model: str = Field(
        description="Configured model identifier.",
        examples=["openai/gpt-oss-20b"],
    )
    host: str = Field(
        description="Provider host from the configured base URL, without its path.",
        examples=["api.groq.com"],
    )
    context_tokens: int = Field(
        description="Configured context window in tokens.",
        examples=[8192],
    )
    max_output_tokens: int = Field(
        description="Configured maximum output size in tokens.",
        examples=[1024],
    )
    api_key_set: bool = Field(
        description="Whether a provider API key is configured; the key is never returned.",
        examples=[True],
    )
