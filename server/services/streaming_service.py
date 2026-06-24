"""SSE streaming service for real-time question delivery.

Delegates to the orchestrator's ``stream_question()`` generator which handles:
    - Pre-warmed first question (sub-200ms first-token)
    - Word-level jieba chunking (natural reading rhythm)
    - Output guard PII sanitization on every chunk
"""

from typing import AsyncGenerator

from fastapi.responses import StreamingResponse


async def sse_generator(
    orchestrator,
    session,
    db_session,
) -> AsyncGenerator[str, None]:
    """Generate SSE events by delegating to the orchestrator's stream_question.

    The orchestrator handles pre-warmup, word-level chunking, guardrails,
    and Redis persistence internally.
    """
    async for sse_event in orchestrator.stream_question(session, db_session):
        yield sse_event


def create_sse_response(orchestrator, session, db_session) -> StreamingResponse:
    """Create a StreamingResponse for SSE question delivery."""
    return StreamingResponse(
        sse_generator(orchestrator, session, db_session),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
