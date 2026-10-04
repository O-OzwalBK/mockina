from uuid import UUID, uuid4

from pydantic import Field

from contracts.common import ImmutableModel

MAX_QUESTION_TEXT_LENGTH = 1_000
MAX_SKILL_ID_LENGTH = 100


class Question(ImmutableModel):
    """One question the interviewer asks during a session."""

    id: UUID = Field(
        description="Globally unique identifier of the question, generated when it is created.",
        default_factory=uuid4,
        examples=["3fa85f64-5717-4562-b3fc-2c963f66afa6"],
    )
    text: str = Field(
        description="The question exactly as it is spoken to the candidate.",
        min_length=1,
        max_length=MAX_QUESTION_TEXT_LENGTH,
        examples=["How does React decide when to re-render a component?"],
    )
    skill_id: str = Field(
        description=(
            "Stable identifier of the skill this question tests. The same skill "
            "keeps the same id across all preparations and sessions."
        ),
        min_length=1,
        max_length=MAX_SKILL_ID_LENGTH,
        examples=["d9b2d6f0-3c1a-4e57-9f0e-8a1b2c3d4e5f"],
    )
    difficulty: int = Field(
        description="Difficulty from 1 (beginner) to 5 (expert).",
        ge=1,
        le=5,
        examples=[2],
    )