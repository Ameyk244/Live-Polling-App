from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models.poll import Poll
from app.models.poll_option import PollOption


def create_poll(
    db: Session,
    code: str,
    question: str,
    options: list[str],
    expires_at: datetime | None = None,
) -> Poll:
    poll = Poll(code=code, question=question, status="open", expires_at=expires_at)
    poll.options = [
        PollOption(text=text, position=index) for index, text in enumerate(options)
    ]
    db.add(poll)
    db.commit()
    db.refresh(poll)
    return poll


def get_poll_by_code(db: Session, code: str) -> Poll | None:
    stmt = (
        select(Poll)
        .options(joinedload(Poll.options))
        .where(Poll.code == code)
    )
    return db.execute(stmt).unique().scalar_one_or_none()


def get_poll_by_id(db: Session, poll_id: int) -> Poll | None:
    stmt = select(Poll).options(joinedload(Poll.options)).where(Poll.id == poll_id)
    return db.execute(stmt).unique().scalar_one_or_none()


def code_exists(db: Session, code: str) -> bool:
    stmt = select(Poll.id).where(Poll.code == code)
    return db.execute(stmt).scalar_one_or_none() is not None


def close_poll(db: Session, poll: Poll) -> Poll:
    poll.status = "closed"
    poll.closed_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(poll)
    return poll
