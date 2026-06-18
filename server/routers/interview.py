"""Interview API endpoints."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from server.database import get_db
from server.dependencies import get_llm_factory
from server.ai.llm import LLMFactory
from server.services.interview_service import InterviewService, get_interview_service
from server.models.interview import InterviewSession
from server.schemas.interview import (
    InterviewStartRequest,
    InterviewStartResponse,
    AnswerSubmitRequest,
    AnswerSubmitResponse,
    QuestionResponse,
    InterviewSessionResponse,
)
from server.utils.auth import require_user

router = APIRouter(prefix="/interview", tags=["interview"])


@router.post("/start", response_model=InterviewStartResponse)
async def start_interview(
    req: InterviewStartRequest,
    db: AsyncSession = Depends(get_db),
    llm_factory: LLMFactory = Depends(get_llm_factory),
    current_user: dict = Depends(require_user),
):
    """Start a new interview session — auto-bound to current user."""
    service = get_interview_service(llm_factory)
    try:
        session = await service.start_interview(
            db=db,
            user_id=current_user["user_id"],
            resume_id=req.resume_id,
            skill_modules=req.skill_modules,
            difficulty=req.difficulty,
            question_count=req.question_count,
        )
        return InterviewStartResponse(
            session_id=session.id,
            status=session.status,
            message=f"面试已开始！共 {req.question_count} 道题目",
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/history")
async def list_history(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_user),
):
    """List all past interview sessions for current user."""
    result = await db.execute(
        select(InterviewSession)
        .where(InterviewSession.user_id == current_user["user_id"])
        .order_by(InterviewSession.created_at.desc())
        .limit(20)
    )
    sessions = result.scalars().all()
    return {
        "sessions": [
            {
                "session_id": s.id,
                "status": s.status,
                "question_count": s.question_count,
                "difficulty_level": s.difficulty_level,
                "skill_modules": s.skill_modules,
                "started_at": s.started_at.isoformat() if s.started_at else None,
                "ended_at": s.ended_at.isoformat() if s.ended_at else None,
            }
            for s in sessions
        ]
    }


@router.get("/{session_id}", response_model=InterviewSessionResponse)
async def get_session(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    llm_factory: LLMFactory = Depends(get_llm_factory),
):
    """Get interview session status."""
    service = get_interview_service(llm_factory)
    session = await service.get_session(db, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    return InterviewSessionResponse(
        session_id=session.id,
        status=session.status,
        resume_id=session.resume_id,
        question_count=session.question_count,
        current_question_index=session.current_question_index,
        difficulty_level=session.difficulty_level,
        started_at=session.started_at,
        ended_at=session.ended_at,
    )


@router.get("/{session_id}/stream")
async def stream_question(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    llm_factory: LLMFactory = Depends(get_llm_factory),
):
    """SSE endpoint: stream the next question."""
    service = get_interview_service(llm_factory)
    try:
        return await service.get_streaming_response(db, session_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{session_id}/answer", response_model=AnswerSubmitResponse)
async def submit_answer(
    session_id: str,
    req: AnswerSubmitRequest,
    db: AsyncSession = Depends(get_db),
    llm_factory: LLMFactory = Depends(get_llm_factory),
):
    """Submit an answer to the current question."""
    service = get_interview_service(llm_factory)
    try:
        answer = await service.submit_answer(
            db=db,
            session_id=session_id,
            question_id=req.question_id,
            answer_text=req.answer_text,
        )
        # Check if interview is complete
        session = await service.get_session(db, session_id)
        next_ready = (
            session is not None
            and session.status == "active"
            and session.question_count < session.settings.get("question_count", 10)
        )

        return AnswerSubmitResponse(
            answer_id=answer.id,
            status="evaluated" if answer.is_evaluated else "submitted",
            next_question_ready=next_ready,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{session_id}/end")
async def end_interview(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    llm_factory: LLMFactory = Depends(get_llm_factory),
):
    """End the interview session."""
    service = get_interview_service(llm_factory)
    try:
        result = await service.end_interview(db, session_id)
        return {"message": "面试已结束", **result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{session_id}/questions")
async def list_questions(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    llm_factory: LLMFactory = Depends(get_llm_factory),
):
    """Get all questions for a session."""
    service = get_interview_service(llm_factory)
    questions = await service.get_questions(db, session_id)
    return {
        "session_id": session_id,
        "questions": [
            {
                "question_id": q.id,
                "question_text": q.question_text,
                "question_type": q.question_type,
                "skill_module": q.skill_module,
                "difficulty": q.difficulty,
                "order_index": q.order_index,
            }
            for q in questions
        ],
    }
