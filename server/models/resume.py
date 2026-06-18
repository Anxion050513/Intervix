"""Resume model."""
from sqlalchemy import String, Integer, Text, JSON, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from server.models.base import Base, TimestampMixin, gen_uuid


class Resume(Base, TimestampMixin):
    __tablename__ = "resumes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False
    )
    original_filename: Mapped[str] = mapped_column(String(512), nullable=False)
    file_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    parsed_data: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    tech_stack: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    years_experience: Mapped[int] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="pending"
    )
    error_message: Mapped[str] = mapped_column(Text, nullable=True)

    user = relationship("User", back_populates="resumes")
    interview_sessions = relationship("InterviewSession", back_populates="resume")
