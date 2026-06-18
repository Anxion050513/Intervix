"""Score & report schemas."""
from typing import Optional
from pydantic import BaseModel


class QuestionScore(BaseModel):
    question_id: str
    question_text: str
    question_type: str
    skill_module: str
    user_answer: str
    score: Optional[float] = None
    score_breakdown: Optional[dict] = None
    feedback: Optional[str] = None


class ImprovementSuggestion(BaseModel):
    area: str
    suggestion: str
    priority: str = "medium"  # high / medium / low


class ScoreReport(BaseModel):
    session_id: str
    overall_score: Optional[float] = None
    total_questions: int
    evaluated_questions: int
    dimension_breakdown: Optional[dict] = None
    skill_breakdown: Optional[dict] = None
    questions: list[QuestionScore] = []
    improvement_suggestions: list[ImprovementSuggestion] = []
