"""Resume API endpoints."""
from fastapi import APIRouter, UploadFile, File, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from server.database import get_db
from server.dependencies import get_llm_factory
from server.ai.llm import LLMFactory
from server.services.resume_service import ResumeService, get_resume_service
from server.schemas.resume import ResumeUploadResponse, ResumeAnalysis
from server.utils.auth import require_user

router = APIRouter(prefix="/resume", tags=["resume"])


@router.post("/upload", response_model=ResumeUploadResponse)
async def upload_resume(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    llm_factory: LLMFactory = Depends(get_llm_factory),
    current_user: dict = Depends(require_user),
):
    """Upload a PDF resume — auto-bound to current user account."""
    if not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")

    content = await file.read()
    if len(content) > 10 * 1024 * 1024:  # 10MB limit
        raise HTTPException(status_code=400, detail="File too large (max 10MB)")

    service = get_resume_service(llm_factory)
    resume = await service.upload_resume(
        db=db,
        user_id=current_user["user_id"],
        filename=file.filename,
        file_content=content,
    )

    return ResumeUploadResponse(
        resume_id=resume.id,
        status=resume.status,
        message="Resume uploaded successfully. Analysis in progress."
        if resume.status == "processing"
        else f"Analysis {resume.status}",
    )


@router.get("/my", response_model=ResumeAnalysis)
async def get_my_resume(
    db: AsyncSession = Depends(get_db),
    llm_factory: LLMFactory = Depends(get_llm_factory),
    current_user: dict = Depends(require_user),
):
    """Get current user's latest parsed resume (auto-bound)."""
    from sqlalchemy import select
    from server.models.resume import Resume

    result = await db.execute(
        select(Resume)
        .where(Resume.user_id == current_user["user_id"], Resume.status == "completed")
        .order_by(Resume.created_at.desc())
        .limit(1)
    )
    resume = result.scalar_one_or_none()

    if not resume:
        raise HTTPException(status_code=404, detail="未找到已解析的简历，请先上传简历")

    return _build_resume_response(resume)


@router.get("/{resume_id}", response_model=ResumeAnalysis)
async def get_resume(
    resume_id: str,
    db: AsyncSession = Depends(get_db),
    llm_factory: LLMFactory = Depends(get_llm_factory),
    current_user: dict = Depends(require_user),
):
    """Get a specific resume (must belong to current user)."""
    service = get_resume_service(llm_factory)
    resume = await service.get_resume(db, resume_id)

    if not resume:
        raise HTTPException(status_code=404, detail="Resume not found")
    if resume.user_id != current_user["user_id"]:
        raise HTTPException(status_code=403, detail="Access denied")

    return _build_resume_response(resume)


@router.get("/{resume_id}/analysis", response_model=ResumeAnalysis)
async def get_resume_analysis(
    resume_id: str,
    db: AsyncSession = Depends(get_db),
    llm_factory: LLMFactory = Depends(get_llm_factory),
    current_user: dict = Depends(require_user),
):
    """Get full resume analysis result."""
    return await get_resume(resume_id, db, llm_factory, current_user)


def _build_resume_response(resume) -> ResumeAnalysis:
    """Build ResumeAnalysis response from a Resume ORM object."""
    return ResumeAnalysis(
        resume_id=resume.id,
        status=resume.status,
        personal_info={
            "name": resume.parsed_data.get("name", ""),
            "email": resume.parsed_data.get("email"),
            "phone": resume.parsed_data.get("phone"),
        },
        tech_stack=resume.tech_stack,
        years_experience=resume.years_experience,
        work_history=resume.parsed_data.get("work_history", []),
        education=resume.parsed_data.get("education", []),
        error_message=resume.error_message,
    )

