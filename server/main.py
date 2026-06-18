"""FastAPI application entry point."""
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from server.config import settings
from server.database import init_db
from server.routers import health, resume, interview, score, auth


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifecycle: startup / shutdown."""
    # Startup
    os.environ["HF_ENDPOINT"] = settings.hf_endpoint  # HuggingFace mirror for China
    os.makedirs(settings.upload_dir, exist_ok=True)
    os.makedirs(settings.chroma_persist_dir, exist_ok=True)
    await init_db()

    # Initialize skills
    from server.dependencies import get_llm_factory
    from server.ai.skills.init_skills import register_all_skills
    llm_factory = get_llm_factory()
    register_all_skills(llm_factory)

    # Initialize LangFuse observability (no-op if not configured)
    from server.observability.langfuse_client import get_langfuse_client
    langfuse_mgr = get_langfuse_client()
    if langfuse_mgr.enabled:
        import logging
        logging.getLogger(__name__).info("LangFuse observability enabled")

    yield
    # Shutdown
    from server.database import engine
    await engine.dispose()


app = FastAPI(
    title="AI Interviewer",
    description="AI 智能面试官系统",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS — allow Vue dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:3000",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(health.router, prefix="/api/v1")
app.include_router(auth.router, prefix="/api/v1")
app.include_router(resume.router, prefix="/api/v1")
app.include_router(interview.router, prefix="/api/v1")
app.include_router(score.router, prefix="/api/v1")

# Observability admin routes (traces + eval)
from server.observability.router import router as observability_router
app.include_router(observability_router, prefix="/api/v1")


@app.get("/")
async def root():
    return {"service": "AI Interviewer", "version": "0.1.0"}
