from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import AlreadyAnsweredError
from app.models.answer import Answer
from app.models.poll_option import PollOption


def has_answered(db: Session, poll_id: int, participant_id: int) -> bool:
    stmt = select(Answer.id).where(
        Answer.poll_id == poll_id, Answer.participant_id == participant_id
    )
    return db.execute(stmt).scalar_one_or_none() is not None


def get_option(db: Session, option_id: int, poll_id: int) -> PollOption | None:
    stmt = select(PollOption).where(
        PollOption.id == option_id, PollOption.poll_id == poll_id
    )
    return db.execute(stmt).scalar_one_or_none()


def create_answer(db: Session, poll_id: int, participant_id: int, option_id: int) -> Answer:
    answer = Answer(poll_id=poll_id, participant_id=participant_id, option_id=option_id)
    db.add(answer)
    try:
        db.commit()
    except IntegrityError as exc:
        # A concurrent request for the same participant can slip past the
        # has_answered() check in the service layer and race to commit first;
        # the DB's (poll_id, participant_id) unique constraint is the real
        # guard, so translate its violation into the same domain error.
        db.rollback()
        raise AlreadyAnsweredError("Participant has already answered this poll") from exc
    db.refresh(answer)
    return answer


def get_tally(db: Session, poll_id: int) -> list[tuple[PollOption, int]]:
    stmt = (
        select(PollOption, func.count(Answer.id))
        .outerjoin(Answer, Answer.option_id == PollOption.id)
        .where(PollOption.poll_id == poll_id)
        .group_by(PollOption.id)
        .order_by(PollOption.position)
    )
    return list(db.execute(stmt).all())


def count_answers(db: Session, poll_id: int) -> int:
    stmt = select(func.count(Answer.id)).where(Answer.poll_id == poll_id)
    return db.execute(stmt).scalar_one()


def get_first_and_last_answer_times(
    db: Session, poll_id: int
) -> tuple[datetime | None, datetime | None]:
    stmt = select(func.min(Answer.created_at), func.max(Answer.created_at)).where(
        Answer.poll_id == poll_id
    )
    first, last = db.execute(stmt).one()
    return first, last
