"""Resume schemas."""
from typing import Optional
from datetime import datetime
from pydantic import BaseModel


class TechItem(BaseModel):
    name: str
    proficiency: str  # beginner / intermediate / advanced / expert
    years: Optional[int] = None


class ResumeAnalysis(BaseModel):
    resume_id: str
    status: str
    personal_info: Optional[dict] = None
    tech_stack: list[TechItem] = []
    years_experience: Optional[int] = None
    work_history: list[dict] = []
    education: list[dict] = []
    error_message: Optional[str] = None


class ResumeUploadResponse(BaseModel):
    resume_id: str
    status: str
    message: str


class ResumeStatus(BaseModel):
    resume_id: str
    status: str
    original_filename: str
    created_at: datetime
