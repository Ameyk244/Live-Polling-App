from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class PollOptionResponse(BaseModel):
    id: int
    text: str
    position: int

    model_config = {"from_attributes": True}


class PollResponse(BaseModel):
    id: int
    code: str
    question: str
    status: str
    created_at: datetime
    closed_at: datetime | None
    options: list[PollOptionResponse]

    model_config = {"from_attributes": True}


class CreatePollRequest(BaseModel):
    question: str = Field(min_length=1, max_length=500)
    options: list[str] = Field(min_length=2)

    @field_validator("options")
    @classmethod
    def options_not_blank(cls, value: list[str]) -> list[str]:
        cleaned = [option.strip() for option in value]
        if any(not option for option in cleaned):
            raise ValueError("Options must not be blank")
        return cleaned


class CreatePollResponse(BaseModel):
    code: str
    host_token: str
    poll: PollResponse


class OptionTally(BaseModel):
    option_id: int
    text: str
    position: int
    count: int


class PollResultsResponse(BaseModel):
    code: str
    question: str
    status: str
    tally: list[OptionTally]
