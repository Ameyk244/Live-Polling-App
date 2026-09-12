from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Answer(Base):
    __tablename__ = "answers"
    __table_args__ = (UniqueConstraint("poll_id", "participant_id", name="uq_answer_poll_participant"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    poll_id: Mapped[int] = mapped_column(ForeignKey("polls.id"), nullable=False)
    participant_id: Mapped[int] = mapped_column(ForeignKey("participants.id"), nullable=False)
    option_id: Mapped[int] = mapped_column(ForeignKey("poll_options.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )

    poll = relationship("Poll", back_populates="answers")
    participant = relationship("Participant", back_populates="answer")
    option = relationship("PollOption", back_populates="answers")
