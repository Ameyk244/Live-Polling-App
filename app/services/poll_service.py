import csv
import io
import logging
import random
import string
from datetime import datetime, timedelta

from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.core.exceptions import NotFoundError, PollClosedError, UnauthorizedError
from app.core.security import HostTokenPayload, create_host_token, create_participant_token
from app.models.participant import Participant
from app.models.poll import Poll
from app.repositories import answer_repository, participant_repository, poll_repository
from app.schemas.poll import OptionTally
from app.services import auth_service
from app.sockets import sio

logger = logging.getLogger(__name__)

CODE_ALPHABET = string.ascii_uppercase + string.digits
CODE_LENGTH = 6


def _generate_unique_code(db: Session) -> str:
    for _ in range(20):
        code = "".join(random.choices(CODE_ALPHABET, k=CODE_LENGTH))
        if not poll_repository.code_exists(db, code):
            return code
    raise RuntimeError("Could not generate a unique poll code")


def create_poll(
    db: Session, question: str, options: list[str], duration_minutes: int | None = None
) -> tuple[Poll, str]:
    code = _generate_unique_code(db)
    expires_at = (
        datetime.utcnow() + timedelta(minutes=duration_minutes)
        if duration_minutes is not None
        else None
    )
    poll = poll_repository.create_poll(
        db, code=code, question=question, options=options, expires_at=expires_at
    )
    host_token = create_host_token(poll.id)
    logger.info("poll created code=%s poll_id=%s", poll.code, poll.id)
    return poll, host_token


def get_poll_by_code(db: Session, code: str) -> Poll:
    poll = poll_repository.get_poll_by_code(db, code)
    if poll is None:
        raise NotFoundError(f"No poll found for code {code}")
    return poll


def get_tally(db: Session, poll_id: int) -> list[OptionTally]:
    rows = answer_repository.get_tally(db, poll_id)
    return [
        OptionTally(option_id=option.id, text=option.text, position=option.position, count=count)
        for option, count in rows
    ]


def _apply_lazy_expiry_sync(db: Session, poll: Poll) -> tuple[Poll, bool]:
    if poll.status == "open" and poll.expires_at is not None and datetime.utcnow() >= poll.expires_at:
        poll = poll_repository.close_poll(db, poll)
        logger.info("poll auto-expired code=%s poll_id=%s", poll.code, poll.id)
        return poll, True
    return poll, False


async def enforce_expiry(db: Session, poll: Poll) -> Poll:
    """Deliberate simplification: no background scheduler/cron job checks
    expiry server-side. Instead, every read of or action on a poll (REST GET,
    join_poll, join_as_host, submit_answer) calls this first — if the poll's
    optional duration has elapsed, it's closed here, at the moment of that
    request, exactly like a manual close (same DB update, same poll_closed
    broadcast). Expiry therefore takes effect at the next real interaction
    with the poll, not at a precise wall-clock instant."""
    poll, expired = await run_in_threadpool(_apply_lazy_expiry_sync, db, poll)
    if expired:
        await sio.emit("poll_closed", {"code": poll.code}, room=poll.code)
    return poll


def _close_poll_sync(db: Session, code: str, host_token: str) -> Poll:
    poll = get_poll_by_code(db, code)
    claims = auth_service.authorize_host(host_token, expected_poll_id=poll.id)
    if claims.poll_id != poll.id:
        raise UnauthorizedError("Token does not match this poll")
    if poll.status != "open":
        raise PollClosedError("This poll is already closed")

    poll = poll_repository.close_poll(db, poll)
    logger.info("poll closed code=%s poll_id=%s", poll.code, poll.id)
    return poll


async def close_poll(db: Session, code: str, host_token: str) -> Poll:
    # The DB work above is synchronous SQLAlchemy; run it on a thread so it
    # doesn't block the event loop, then do the async broadcast out here.
    poll = await run_in_threadpool(_close_poll_sync, db, code, host_token)
    await sio.emit("poll_closed", {"code": poll.code}, room=poll.code)
    return poll


def _authorize_host_for_poll_sync(db: Session, code: str, host_token: str) -> Poll:
    """Fetch a poll and verify host_token is a host token for THIS poll —
    same check as _close_poll_sync's key line, reused for read-only
    host-only endpoints (export, analytics) that don't mutate the poll."""
    poll = get_poll_by_code(db, code)
    claims = auth_service.authorize_host(host_token, expected_poll_id=poll.id)
    if claims.poll_id != poll.id:
        raise UnauthorizedError("Token does not match this poll")
    return poll


async def get_export_data(db: Session, code: str, host_token: str) -> tuple[Poll, list[OptionTally]]:
    poll = await run_in_threadpool(_authorize_host_for_poll_sync, db, code, host_token)
    poll = await enforce_expiry(db, poll)
    tally = await run_in_threadpool(get_tally, db, poll.id)
    return poll, tally


def build_export_csv(poll: Poll, tally: list[OptionTally]) -> str:
    """One row per option (option_text,vote_count), with the question and
    total votes surfaced as '#'-prefixed metadata lines above the data rows —
    still valid, parseable CSV since csv readers treat them as ordinary rows
    unless the caller chooses to skip '#' lines."""
    total_votes = sum(option.count for option in tally)
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow([f"# question: {poll.question}"])
    writer.writerow([f"# total_votes: {total_votes}"])
    writer.writerow(["option_text", "vote_count"])
    for option in tally:
        writer.writerow([option.text, option.count])
    return buffer.getvalue()


async def get_poll_analytics(db: Session, code: str, host_token: str) -> dict:
    poll = await run_in_threadpool(_authorize_host_for_poll_sync, db, code, host_token)
    poll = await enforce_expiry(db, poll)
    tally = await run_in_threadpool(get_tally, db, poll.id)
    joined = await run_in_threadpool(participant_repository.count_participants, db, poll.id)
    answered = await run_in_threadpool(answer_repository.count_answers, db, poll.id)
    first_answer, last_answer = await run_in_threadpool(
        answer_repository.get_first_and_last_answer_times, db, poll.id
    )
    response_rate = (answered / joined * 100) if joined > 0 else 0.0
    # Reference point: poll.created_at. This app has no separate "publish"
    # step — a poll is open from the moment it's created — so created_at is
    # the simplest correct reference for time-to-first/last-vote.
    seconds_to_first = (first_answer - poll.created_at).total_seconds() if first_answer else None
    seconds_to_last = (last_answer - poll.created_at).total_seconds() if last_answer else None
    return {
        "code": poll.code,
        "question": poll.question,
        "status": poll.status,
        "participants_joined": joined,
        "participants_answered": answered,
        "response_rate_percent": response_rate,
        "seconds_to_first_vote": seconds_to_first,
        "seconds_to_last_vote": seconds_to_last,
        "tally": tally,
    }


async def join_poll(db: Session, poll_code: str, display_name: str) -> tuple[Poll, Participant, str]:
    poll = await run_in_threadpool(get_poll_by_code, db, poll_code)
    poll = await enforce_expiry(db, poll)
    if poll.status != "open":
        raise PollClosedError("This poll is closed")

    participant = await run_in_threadpool(
        participant_repository.create_participant, db, poll.id, display_name
    )
    token = create_participant_token(poll.id, participant.id)
    logger.info(
        "participant joined poll_id=%s participant_id=%s", poll.id, participant.id
    )
    return poll, participant, token


async def join_as_host(db: Session, host_token: str) -> tuple[Poll, HostTokenPayload]:
    claims = auth_service.authorize_host(host_token)
    poll = await run_in_threadpool(poll_repository.get_poll_by_id, db, claims.poll_id)
    if poll is None:
        raise NotFoundError("Poll not found")
    poll = await enforce_expiry(db, poll)
    return poll, claims
