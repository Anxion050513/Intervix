"""Health check endpoint."""
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from server.database import get_db
from server.schemas.common import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health_check(db: AsyncSession = Depends(get_db)):
    response = HealthResponse(status="ok")

    # Check MySQL
    try:
        await db.execute(text("SELECT 1"))
        response.mysql = "ok"
    except Exception as e:
        response.status = "degraded"
        response.mysql = f"error: {e}"

    # Check Redis (via SessionCache singleton — reuses the shared connection)
    try:
        from server.services.session_cache import SessionCache
        cache = await SessionCache.create()
        if await cache.ping():
            response.redis = "ok"
        else:
            response.status = "degraded"
            response.redis = "error: ping returned False (fallback in-memory mode)"
    except Exception as e:
        response.status = "degraded"
        response.redis = f"error: {e}"

    # Check LLM (non-blocking)
    try:
        from server.ai.llm import LLMFactory
        from server.config import settings
        factory = LLMFactory(
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url,
            model=settings.llm_model,
        )
        llm = factory.get_chat_model()
        await llm.ainvoke("ping")
        response.llm = "ok"
    except Exception as e:
        response.status = "degraded"
        response.llm = f"error: {e}"

    return response
