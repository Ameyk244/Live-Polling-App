from pydantic import BaseModel, Field


class JoinPollPayload(BaseModel):
    poll_code: str = Field(min_length=1, max_length=6)
    display_name: str = Field(min_length=1, max_length=100)


class JoinAsHostPayload(BaseModel):
    token: str = Field(min_length=1)
