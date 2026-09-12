import logging
import random
import string

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


def create_poll(db: Session, question: str, options: list[str]) -> tuple[Poll, str]:
    code = _generate_unique_code(db)
    poll = poll_repository.create_poll(db, code=code, question=question, options=options)
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


def get_results(db: Session, code: str) -> tuple[Poll, list[OptionTally]]:
    poll = get_poll_by_code(db, code)
    tally = get_tally(db, poll.id)
    return poll, tally


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


def join_poll(db: Session, poll_code: str, display_name: str) -> tuple[Poll, Participant, str]:
    poll = get_poll_by_code(db, poll_code)
    if poll.status != "open":
        raise PollClosedError("This poll is closed")

    participant = participant_repository.create_participant(db, poll.id, display_name)
    token = create_participant_token(poll.id, participant.id)
    logger.info(
        "participant joined poll_id=%s participant_id=%s", poll.id, participant.id
    )
    return poll, participant, token


def join_as_host(db: Session, host_token: str) -> tuple[Poll, HostTokenPayload]:
    claims = auth_service.authorize_host(host_token)
    poll = poll_repository.get_poll_by_id(db, claims.poll_id)
    if poll is None:
        raise NotFoundError("Poll not found")
    return poll, claims
