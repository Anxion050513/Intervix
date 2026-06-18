"""Admin API routes for observability (traces) and eval framework."""
import json
import os
import logging

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from server.dependencies import get_llm_factory
from server.ai.llm import LLMFactory

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])


# === Pydantic schemas ===

class TraceSummary(BaseModel):
    trace_id: str = ""
    trace_name: str = ""
    timestamp: str = ""
    latency_ms: float = 0.0
    total_tokens: int = 0
    total_cost: float = 0.0
    phase: str = ""
    session_id: str = ""


class TraceListResponse(BaseModel):
    traces: list[TraceSummary]
    total: int
    page: int
    page_size: int


class DimDiff(BaseModel):
    dimension: str
    expected: float
    actual: float
    diff: float


class EvalTestResult(BaseModel):
    test_id: str
    skill_module: str
    expected_score: float
    actual_score: float | None
    score_diff: float | None
    dimension_diffs: list[DimDiff]
    passed: bool


class EvalReport(BaseModel):
    total_tests: int
    passed: int
    failed: int
    avg_score_diff: float
    results: list[EvalTestResult]
    summary: str


# === Trace endpoint ===

@router.get("/traces", response_model=TraceListResponse)
async def list_traces(
    session_id: str | None = Query(None),
    phase: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """List recent LLM call traces from LangFuse.

    Returns an empty list when LangFuse is not configured.
    """
    from server.observability.langfuse_client import get_langfuse_client

    mgr = get_langfuse_client()
    if not mgr.enabled or not mgr.client:
        return TraceListResponse(
            traces=[], total=0, page=page, page_size=page_size
        )

    try:
        # LangFuse client.fetch_traces() returns paginated traces
        params = {"page": page, "limit": page_size}
        if phase:
            params["tags"] = [phase]

        response = mgr.client.fetch_traces(**params)

        traces = []
        for t in response.data:
            traces.append(TraceSummary(
                trace_id=t.id,
                trace_name=t.name or "",
                timestamp=t.timestamp.isoformat() if t.timestamp else "",
                latency_ms=getattr(t, "latency", 0) or 0,
                total_tokens=getattr(t, "totalTokens", 0) or 0,
                total_cost=getattr(t, "totalCost", 0.0) or 0.0,
                phase=next(iter(t.tags or []), ""),
                session_id=(t.metadata or {}).get("session_id", ""),
            ))

        return TraceListResponse(
            traces=traces,
            total=response.meta.total_items if response.meta else len(traces),
            page=page,
            page_size=page_size,
        )
    except Exception as e:
        logger.warning("Failed to fetch LangFuse traces: %s", e)
        return TraceListResponse(
            traces=[], total=0, page=page, page_size=page_size
        )


# === Eval endpoints ===

@router.post("/eval/run", response_model=EvalReport)
async def run_eval(
    llm_factory: LLMFactory = Depends(get_llm_factory),
):
    """Run the golden dataset evaluation against current LLM prompts."""
    from server.observability.eval_runner import EvalRunner

    runner = EvalRunner(llm_factory)
    return await runner.run_eval()


@router.get("/eval/dataset")
async def get_eval_dataset():
    """View the golden dataset (expected scores hidden)."""
    dataset_path = os.path.join(os.path.dirname(__file__), "eval_dataset.json")

    if not os.path.exists(dataset_path):
        return {"count": 0, "tests": [], "error": "Dataset not found"}

    with open(dataset_path, "r", encoding="utf-8") as f:
        dataset = json.load(f)

    return {
        "count": len(dataset),
        "tests": [
            {
                "test_id": t["test_id"],
                "skill_module": t["skill_module"],
                "question_text": t["question_text"][:200],
                "user_answer": t["user_answer"][:200],
                "key_points": t.get("key_points", []),
                "context": t.get("context", {}),
            }
            for t in dataset
        ],
    }
