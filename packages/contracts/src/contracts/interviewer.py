from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field


class Question(BaseModel):
    """Model of a question that the interviewer asks during a session."""

    model_config= ConfigDict(str_strip_whitespace=True)

    id: UUID = Field(
        default_factory=uuid4,
        description="Globally unique identifier of the question, generated when it is created.",
        examples=["3fa85f64-5717-4562-b3fc-2c963f66afa6"],
    )
    skill_id: str = Field(
        min_length=1,
        description="Stable identifier of the skill this question tests. The same skill keeps the same id across all preparations and sessions."
        )
    text: str = Field(
        description="The actual question presented to the user.",
        min_length=1,
        examples=["How does React decide when to re-render a component?"]
    )
    topic: str = Field(
        description="The skill or subject the question tests, used for the topic breakdown.",
        min_length=1,
        examples=["React rendering"]
    )
    difficulty: int = Field(
        ge=1,
        le=5,
        description="Difficulty from 1 (beginner) to 5 (expert).",
        examples=[2],
    )