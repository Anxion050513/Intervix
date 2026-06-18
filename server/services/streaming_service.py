"""SSE streaming service for real-time question delivery."""
import json
import asyncio
from typing import AsyncGenerator

from fastapi.responses import StreamingResponse


async def sse_generator(
    orchestrator,
    session,
    db_session,
) -> AsyncGenerator[str, None]:
    """Generate SSE events for streaming question delivery."""
    import json

    gen_q, state = await orchestrator.next_question(session, db_session)

    if gen_q is None:
        yield f"data: {json.dumps({'type': 'interview_complete', 'state': state})}\n\n"
        return

    # Get the current question from session data
    session_data = orchestrator.get_session_data(session.id)
    current_question = session_data.get("current_question") if session_data else None
    question_id = current_question.id if current_question else ""

    # Send metadata
    meta = {
        "type": "question_meta",
        "question_id": question_id,
        "question_type": gen_q.question_type,
        "skill_module": state,
        "difficulty": session_data["ctx"].difficulty if session_data else "medium",
    }
    yield f"data: {json.dumps(meta, ensure_ascii=False)}\n\n"

    # Stream the question text — character by character for typing effect
    text = gen_q.text
    for i in range(0, len(text), 2):
        chunk = text[i:i+2]
        yield f"data: {json.dumps({'type': 'token', 'content': chunk}, ensure_ascii=False)}\n\n"
        await asyncio.sleep(0.03)  # ~60 chars/sec typing speed

    yield f"data: {json.dumps({'type': 'question_complete'}, ensure_ascii=False)}\n\n"


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
