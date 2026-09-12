from fastapi import APIRouter, Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.database import get_db
from app.schemas.poll import (
    CreatePollRequest,
    CreatePollResponse,
    PollResponse,
    PollResultsResponse,
)
from app.services import poll_service

router = APIRouter(prefix="/polls", tags=["polls"])
bearer_scheme = HTTPBearer()


@router.post("", response_model=CreatePollResponse)
def create_poll(body: CreatePollRequest, db: Session = Depends(get_db)):
    poll, host_token = poll_service.create_poll(
        db, question=body.question, options=body.options, duration_minutes=body.duration_minutes
    )
    return CreatePollResponse(
        code=poll.code, host_token=host_token, poll=PollResponse.model_validate(poll)
    )


@router.get("/{code}", response_model=PollResponse)
async def get_poll(code: str, db: Session = Depends(get_db)):
    poll = await run_in_threadpool(poll_service.get_poll_by_code, db, code)
    poll = await poll_service.enforce_expiry(db, poll)
    return PollResponse.model_validate(poll)


@router.get("/{code}/results", response_model=PollResultsResponse)
async def get_results(code: str, db: Session = Depends(get_db)):
    poll = await run_in_threadpool(poll_service.get_poll_by_code, db, code)
    poll = await poll_service.enforce_expiry(db, poll)
    tally = await run_in_threadpool(poll_service.get_tally, db, poll.id)
    return PollResultsResponse(code=poll.code, question=poll.question, status=poll.status, tally=tally)


@router.post("/{code}/close", response_model=PollResponse)
async def close_poll(
    code: str,
    db: Session = Depends(get_db),
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
):
    poll = await poll_service.close_poll(db, code, credentials.credentials)
    return PollResponse.model_validate(poll)
