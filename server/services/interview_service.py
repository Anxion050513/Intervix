"""Interview session service."""
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from server.models.interview import InterviewSession
from server.models.question import Question
from server.models.answer import Answer
from server.models.resume import Resume
from server.ai.llm import LLMFactory
from server.ai.orchestrator import get_orchestrator
from server.ai.skills.registry import skill_registry


class InterviewService:
    """Manages interview session lifecycle."""

    def __init__(self, llm_factory: LLMFactory):
        self.llm_factory = llm_factory

    async def start_interview(
        self,
        db: AsyncSession,
        user_id: str,
        resume_id: str,
        skill_modules: list[str] | None = None,
        difficulty: str = "medium",
        question_count: int = 10,
    ) -> InterviewSession:
        """Start a new interview session.

        Args:
            db: Database session.
            user_id: The user starting the interview.
            resume_id: The parsed resume to base questions on.
            skill_modules: Which skill modules to include (None = all).
            difficulty: Starting difficulty.
            question_count: Target number of questions.

        Returns:
            The created InterviewSession.
        """
        # Fetch resume
        result = await db.execute(select(Resume).where(Resume.id == resume_id))
        resume = result.scalar_one_or_none()
        if not resume:
            raise ValueError(f"Resume {resume_id} not found")
        if resume.status != "completed":
            raise ValueError(f"Resume not fully parsed. Status: {resume.status}")

        # Default to all available skills
        if not skill_modules:
            skill_modules = [s.name for s in skill_registry.get_all()]

        # Create session
        session = InterviewSession(
            id=str(uuid.uuid4()),
            user_id=user_id,
            resume_id=resume_id,
            status="active",
            skill_modules=skill_modules,
            difficulty_level=difficulty,
            settings={"question_count": question_count},
            started_at=datetime.utcnow(),
        )
        db.add(session)
        await db.flush()

        # Initialize orchestrator
        orchestrator = get_orchestrator(self.llm_factory)
        await orchestrator.start_session(
            session=session,
            resume_data=resume.parsed_data,
            tech_stack=resume.tech_stack,
            years_experience=resume.years_experience,
        )

        return session

    async def get_session(
        self, db: AsyncSession, session_id: str
    ) -> Optional[InterviewSession]:
        """Get an interview session by ID."""
        result = await db.execute(
            select(InterviewSession).where(InterviewSession.id == session_id)
        )
        return result.scalar_one_or_none()

    async def get_next_question(
        self, db: AsyncSession, session_id: str
    ):
        """Get the next question for an active session."""
        session = await self.get_session(db, session_id)
        if not session:
            raise ValueError("Session not found")
        if session.status != "active":
            raise ValueError(f"Session is not active. Status: {session.status}")

        orchestrator = get_orchestrator(self.llm_factory)
        return await orchestrator.next_question(session, db)

    async def submit_answer(
        self, db: AsyncSession, session_id: str, question_id: str, answer_text: str
    ) -> Answer:
        """Submit an answer to a question."""
        session = await self.get_session(db, session_id)
        if not session:
            raise ValueError("Session not found")

        orchestrator = get_orchestrator(self.llm_factory)
        answer = await orchestrator.submit_answer(
            session, question_id, answer_text, db
        )
        if not answer:
            raise ValueError("Failed to submit answer")
        return answer

    async def end_interview(
        self, db: AsyncSession, session_id: str
    ) -> dict:
        """End an interview session."""
        session = await self.get_session(db, session_id)
        if not session:
            raise ValueError("Session not found")

        orchestrator = get_orchestrator(self.llm_factory)
        return await orchestrator.end_session(session, db)

    async def get_streaming_response(self, db: AsyncSession, session_id: str):
        """Get an SSE streaming response for the next question."""
        session = await self.get_session(db, session_id)
        if not session:
            raise ValueError("Session not found")

        orchestrator = get_orchestrator(self.llm_factory)
        from server.services.streaming_service import create_sse_response
        return create_sse_response(orchestrator, session, db)

    async def get_questions(
        self, db: AsyncSession, session_id: str
    ) -> list[Question]:
        """Get all questions for a session."""
        result = await db.execute(
            select(Question)
            .where(Question.session_id == session_id)
            .order_by(Question.order_index)
        )
        return list(result.scalars().all())


# Singleton accessor
_interview_service: Optional[InterviewService] = None


def get_interview_service(llm_factory: LLMFactory) -> InterviewService:
    global _interview_service
    if _interview_service is None:
        _interview_service = InterviewService(llm_factory)
    return _interview_service
