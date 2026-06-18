"""Event data classes for the interview lifecycle."""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class InterviewEvent:
    """Base event."""
    session_id: str
    timestamp: datetime = field(default_factory=datetime.utcnow)


@dataclass
class InterviewStarted(InterviewEvent):
    resume_data: dict = field(default_factory=dict)
    skill_modules: list = field(default_factory=list)


@dataclass
class QuestionGenerated(InterviewEvent):
    question_id: str = ""
    question_text: str = ""
    question_type: str = ""
    skill_name: str = ""
    difficulty: str = "medium"
    order_index: int = 0


@dataclass
class AnswerSubmitted(InterviewEvent):
    question_id: str = ""
    answer_text: str = ""


@dataclass
class AnswerScored(InterviewEvent):
    question_id: str = ""
    score: float = 0.0
    feedback: str = ""


@dataclass
class InterviewEnded(InterviewEvent):
    final_report: dict = field(default_factory=dict)
