"""Score & report API endpoints."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from server.database import get_db
from server.dependencies import get_llm_factory
from server.ai.llm import LLMFactory
from server.services.scoring_service import ScoringService, get_scoring_service

router = APIRouter(prefix="/interview", tags=["score"])


@router.get("/{session_id}/report")
async def get_report(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    llm_factory: LLMFactory = Depends(get_llm_factory),
):
    """Get the full interview score report."""
    service = get_scoring_service(llm_factory)
    try:
        report = await service.generate_report(db, session_id)
        return report
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/{session_id}/report/improvements")
async def get_improvements(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    llm_factory: LLMFactory = Depends(get_llm_factory),
):
    """Get only the improvement suggestions."""
    service = get_scoring_service(llm_factory)
    try:
        report = await service.generate_report(db, session_id)
        return {
            "session_id": session_id,
            "overall_score": report.overall_score,
            "improvement_suggestions": report.improvement_suggestions,
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
