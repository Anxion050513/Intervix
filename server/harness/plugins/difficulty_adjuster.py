"""Difficulty adjuster plugin — adapts difficulty based on performance."""
from server.harness.hooks import InterviewHooks


class DifficultyAdjusterPlugin(InterviewHooks):
    """Automatically adjusts interview difficulty based on running average score."""

    def __init__(self):
        self._running_scores: dict[str, list[float]] = {}

    async def on_answer_scored(self, session_id, score, **kwargs):
        if session_id not in self._running_scores:
            self._running_scores[session_id] = []
        self._running_scores[session_id].append(score)

    async def on_difficulty_adjust(self, session_id, running_avg_score):
        """Determine next difficulty based on average score.

        Returns:
            'hard' if avg > 80, 'easy' if avg < 50, 'medium' otherwise.
            None to keep current difficulty.
        """
        if running_avg_score is None:
            return None

        if running_avg_score >= 80:
            return "hard"
        elif running_avg_score < 50:
            return "easy"
        else:
            return "medium"

    async def on_interview_end(self, session_id, final_report):
        self._running_scores.pop(session_id, None)
