import logging
from dataclasses import dataclass

from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.core.exceptions import AlreadyAnsweredError, InvalidOptionError, NotFoundError, PollClosedError
from app.core.rate_limiter import check_submit_cooldown, record_submit
from app.repositories import answer_repository, poll_repository
from app.schemas.poll import OptionTally
from app.services import poll_service

logger = logging.getLogger(__name__)


@dataclass
class SubmitAnswerResult:
    poll_code: str
    tally: list[OptionTally]


def _submit_answer_sync(
    db: Session, poll_id: int, poll_code: str, participant_id: int, option_id: int
) -> SubmitAnswerResult:
    option = answer_repository.get_option(db, option_id, poll_id)
    if option is None:
        raise InvalidOptionError("Selected option does not belong to this poll")

    if answer_repository.has_answered(db, poll_id, participant_id):
        raise AlreadyAnsweredError("Participant has already answered this poll")

    check_submit_cooldown(participant_id)

    answer_repository.create_answer(db, poll_id, participant_id, option_id)
    record_submit(participant_id)
    logger.info(
        "answer submitted poll_id=%s participant_id=%s option_id=%s",
        poll_id,
        participant_id,
        option_id,
    )

    rows = answer_repository.get_tally(db, poll_id)
    tally = [
        OptionTally(option_id=opt.id, text=opt.text, position=opt.position, count=count)
        for opt, count in rows
    ]
    return SubmitAnswerResult(poll_code=poll_code, tally=tally)


async def submit_answer(
    db: Session, poll_id: int, participant_id: int, option_id: int
) -> SubmitAnswerResult:
    poll = await run_in_threadpool(poll_repository.get_poll_by_id, db, poll_id)
    if poll is None:
        raise NotFoundError("Poll not found")
    poll = await poll_service.enforce_expiry(db, poll)
    if poll.status != "open":
        raise PollClosedError("This poll is closed")

    return await run_in_threadpool(_submit_answer_sync, db, poll_id, poll.code, participant_id, option_id)
