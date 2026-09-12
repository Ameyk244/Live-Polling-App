from fastapi import APIRouter, Depends, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.database import get_db
from app.schemas.poll import (
    CreatePollRequest,
    CreatePollResponse,
    ExportOptionResult,
    PollAnalyticsResponse,
    PollExportResponse,
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


@router.get("/{code}/export")
async def export_poll(
    code: str,
    format: str = "json",
    db: Session = Depends(get_db),
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
):
    poll, tally = await poll_service.get_export_data(db, code, credentials.credentials)

    # Default to json on a missing/unrecognized format value rather than 422.
    fmt = format.lower() if isinstance(format, str) else "json"
    if fmt == "csv":
        csv_body = poll_service.build_export_csv(poll, tally)
        return Response(
            content=csv_body,
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="poll_{poll.code}.csv"'},
        )

    total_votes = sum(option.count for option in tally)
    return PollExportResponse(
        code=poll.code,
        question=poll.question,
        status=poll.status,
        created_at=poll.created_at,
        closed_at=poll.closed_at,
        expires_at=poll.expires_at,
        total_votes=total_votes,
        options=[
            ExportOptionResult(text=option.text, position=option.position, vote_count=option.count)
            for option in tally
        ],
    )


@router.get("/{code}/analytics", response_model=PollAnalyticsResponse)
async def get_analytics(
    code: str,
    db: Session = Depends(get_db),
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
):
    data = await poll_service.get_poll_analytics(db, code, credentials.credentials)
    return PollAnalyticsResponse(**data)
