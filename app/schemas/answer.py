from pydantic import BaseModel, Field


class SubmitAnswerPayload(BaseModel):
    token: str = Field(min_length=1)
    option_id: int
