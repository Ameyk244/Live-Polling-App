from datetime import datetime, timezone

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Poll(Base):
    __tablename__ = "polls"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(6), unique=True, index=True, nullable=False)
    question: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[str] = mapped_column(String(10), nullable=False, default="open")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    options = relationship(
        "PollOption", back_populates="poll", cascade="all, delete-orphan", order_by="PollOption.position"
    )
    participants = relationship("Participant", back_populates="poll", cascade="all, delete-orphan")
    answers = relationship("Answer", back_populates="poll", cascade="all, delete-orphan")
