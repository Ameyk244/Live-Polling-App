from sqlalchemy.orm import Session

from app.models.participant import Participant


def create_participant(db: Session, poll_id: int, display_name: str) -> Participant:
    participant = Participant(poll_id=poll_id, display_name=display_name)
    db.add(participant)
    db.commit()
    db.refresh(participant)
    return participant


def get_participant_by_id(db: Session, participant_id: int) -> Participant | None:
    return db.get(Participant, participant_id)
