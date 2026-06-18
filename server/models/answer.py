"""Answer model."""
from datetime import datetime

from sqlalchemy import String, Integer, Text, Boolean, DateTime, Numeric, JSON, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from server.models.base import Base, TimestampMixin, gen_uuid


class Answer(Base, TimestampMixin):
    __tablename__ = "answers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    question_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("questions.id", ondelete="CASCADE"), nullable=False
    )
    user_answer: Mapped[str] = mapped_column(Text, nullable=False)
    score: Mapped[float] = mapped_column(Numeric(5, 2), nullable=True)
    score_breakdown: Mapped[dict] = mapped_column(JSON, nullable=True)
    feedback: Mapped[str] = mapped_column(Text, nullable=True)
    is_evaluated: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    evaluated_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    duration_seconds: Mapped[int] = mapped_column(Integer, nullable=True)

    question = relationship("Question", back_populates="answer")
