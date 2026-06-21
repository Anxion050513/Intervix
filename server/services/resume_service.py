"""Resume processing service."""
import os
import uuid
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from server.config import settings
from server.models.resume import Resume
from server.utils.pdf import extract_text_from_pdf
from server.ai.llm import LLMFactory
from server.ai.prompts.resume_extraction import (
    RESUME_EXTRACTION_PROMPT,
    parser,
)


class ResumeService:
    """Handles resume upload, parsing, and querying."""

    def __init__(self, llm_factory: LLMFactory):
        self.llm_factory = llm_factory

    async def upload_resume(
        self,
        db: AsyncSession,
        user_id: str,
        filename: str,
        file_content: bytes,
    ) -> Resume:
        """Upload a PDF resume, save to disk, and start parsing.

        Args:
            db: Database session.
            user_id: Owner user ID.
            filename: Original filename.
            file_content: Raw PDF bytes.

        Returns:
            The created Resume ORM object.
        """
        # Save file to disk
        resume_id = str(uuid.uuid4())
        ext = os.path.splitext(filename)[1] or ".pdf"
        saved_name = f"{resume_id}{ext}"
        file_path = os.path.join(settings.upload_dir, saved_name)

        os.makedirs(settings.upload_dir, exist_ok=True)
        with open(file_path, "wb") as f:
            f.write(file_content)

        # Create DB record
        resume = Resume(
            id=resume_id,
            user_id=user_id,
            original_filename=filename,
            file_path=file_path,
            status="processing",
        )
        db.add(resume)
        await db.flush()

        # Attempt extraction synchronously for MVP (async task in production)
        try:
            text = extract_text_from_pdf(file_path)
            parsed = await self._parse_with_llm(text, self.llm_factory, resume_id=resume_id)

            resume.parsed_data = parsed.model_dump()
            resume.tech_stack = parsed.tech_stack
            resume.years_experience = parsed.years_experience
            resume.status = "completed"
        except Exception as e:
            resume.status = "failed"
            resume.error_message = str(e)

        await db.flush()
        return resume

    async def _parse_with_llm(self, text: str, llm_factory: LLMFactory, resume_id: str = ""):
        """Send resume text to LLM for structured extraction."""
        # Set trace context for observability
        try:
            from server.observability.callbacks import TraceContext
            TraceContext.set(session_id=f"resume:{resume_id}", phase="extract")
        except Exception:
            pass
        try:
            llm = llm_factory.get_chat_model(temperature=0.1, max_tokens=3000)
            chain = RESUME_EXTRACTION_PROMPT | llm | parser
            return await chain.ainvoke({"resume_text": text[:8000]})
        finally:
            try:
                TraceContext.clear()
            except Exception:
                pass

    async def get_resume(
        self, db: AsyncSession, resume_id: str
    ) -> Optional[Resume]:
        """Get a resume by ID."""
        result = await db.execute(
            select(Resume).where(Resume.id == resume_id)
        )
        return result.scalar_one_or_none()

    async def get_resumes_by_user(
        self, db: AsyncSession, user_id: str, limit: int = 20
    ) -> list[Resume]:
        """Get all resumes for a user."""
        result = await db.execute(
            select(Resume)
            .where(Resume.user_id == user_id)
            .order_by(Resume.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())


# Singleton accessor
_resume_service: Optional[ResumeService] = None


def get_resume_service(llm_factory: LLMFactory) -> ResumeService:
    global _resume_service
    if _resume_service is None:
        _resume_service = ResumeService(llm_factory)
    return _resume_service
