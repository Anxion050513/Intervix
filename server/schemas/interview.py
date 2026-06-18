"""Interview schemas."""
from typing import Optional
from datetime import datetime
from pydantic import BaseModel


class InterviewStartRequest(BaseModel):
    resume_id: str
    skill_modules: Optional[list[str]] = None  # 默认全用
    difficulty: str = "medium"  # easy / medium / hard
    question_count: int = 10


class InterviewStartResponse(BaseModel):
    session_id: str
    status: str
    message: str


class AnswerSubmitRequest(BaseModel):
    question_id: str
    answer_text: str


class AnswerSubmitResponse(BaseModel):
    answer_id: str
    status: str
    next_question_ready: bool = False


class QuestionResponse(BaseModel):
    question_id: str
    session_id: str
    question_text: str
    question_type: str
    skill_module: str
    difficulty: str
    order_index: int
    metadata: dict = {}


class InterviewSessionResponse(BaseModel):
    session_id: str
    status: str
    resume_id: str
    question_count: int
    current_question_index: int
    difficulty_level: str
    started_at: datetime
    ended_at: Optional[datetime] = None
