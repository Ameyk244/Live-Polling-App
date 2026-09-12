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
    expires_at: datetime | None
    options: list[PollOptionResponse]

    model_config = {"from_attributes": True}


class CreatePollRequest(BaseModel):
    question: str = Field(min_length=1, max_length=500)
    options: list[str] = Field(min_length=2)
    duration_minutes: int | None = Field(default=None, ge=1, le=1440)

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


class ExportOptionResult(BaseModel):
    text: str
    position: int
    vote_count: int


class PollExportResponse(BaseModel):
    code: str
    question: str
    status: str
    created_at: datetime
    closed_at: datetime | None
    expires_at: datetime | None
    total_votes: int
    options: list[ExportOptionResult]


class PollAnalyticsResponse(BaseModel):
    code: str
    question: str
    status: str
    participants_joined: int
    participants_answered: int
    response_rate_percent: float
    # Reference point for time-to-first/last-vote: this app has no separate
    # "publish" step, so poll creation and poll "open" are the same moment —
    # created_at is therefore the simplest correct reference timestamp.
    seconds_to_first_vote: float | None
    seconds_to_last_vote: float | None
    tally: list[OptionTally]
