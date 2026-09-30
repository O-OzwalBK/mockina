from pydantic import BaseModel, Field, model_validator


class WordTiming(BaseModel):
    word: str
    start: float = Field(ge=0)
    end: float = Field(ge=0)

    @model_validator(mode='after')
    def validate_endtimestamp(self):
        if self.end > self.start:
            return self
        else:
            raise ValueError(f"end timestamp: ({self.end}s) must be strictly greater than start timestamp: ({self.start}s)")