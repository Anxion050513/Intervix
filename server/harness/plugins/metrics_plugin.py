"""Metrics plugin — tracks interview statistics."""
from server.harness.hooks import InterviewHooks


class MetricsPlugin(InterviewHooks):
    """Collects runtime metrics for interviews."""

    def __init__(self):
        self._metrics: dict[str, dict] = {}

    def _ensure_session(self, session_id: str):
        if session_id not in self._metrics:
            self._metrics[session_id] = {
                "question_count": 0,
                "answer_count": 0,
                "total_score": 0.0,
                "scored_count": 0,
                "errors": 0,
            }

    async def on_question_generated(self, session_id, **kwargs):
        self._ensure_session(session_id)
        self._metrics[session_id]["question_count"] += 1

    async def on_answer_submitted(self, session_id, **kwargs):
        self._ensure_session(session_id)
        self._metrics[session_id]["answer_count"] += 1

    async def on_answer_scored(self, session_id, score, **kwargs):
        self._ensure_session(session_id)
        self._metrics[session_id]["total_score"] += score
        self._metrics[session_id]["scored_count"] += 1

    async def on_error(self, session_id, **kwargs):
        self._ensure_session(session_id)
        self._metrics[session_id]["errors"] += 1

    async def on_interview_end(self, session_id, final_report):
        pass  # Metrics could be persisted here

    def get_session_stats(self, session_id: str) -> dict:
        """Get current stats for a session."""
        m = self._metrics.get(session_id, {})
        scored = m.get("scored_count", 0)
        return {
            "questions_generated": m.get("question_count", 0),
            "answers_submitted": m.get("answer_count", 0),
            "average_score": (
                m.get("total_score", 0) / scored if scored > 0 else 0
            ),
            "errors": m.get("errors", 0),
        }
