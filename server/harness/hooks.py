"""pluggy hook specifications for the interview lifecycle."""
import pluggy

hookspec = pluggy.HookspecMarker("ai_interviewer")


class InterviewHooks:
    """Hook specification for interview events.

    Plugins implement these hooks to react to interview lifecycle events.
    """

    @hookspec
    async def on_interview_start(
        self, session_id: str, resume_data: dict, skill_modules: list
    ):
        """Fired when an interview session starts."""

    @hookspec
    async def on_question_generated(
        self,
        session_id: str,
        question_id: str,
        question_text: str,
        question_type: str,
        skill_name: str,
        difficulty: str,
        order_index: int,
    ):
        """Fired after a skill generates a new question."""

    @hookspec
    async def on_answer_submitted(
        self, session_id: str, question_id: str, answer_text: str
    ):
        """Fired when the user submits an answer."""

    @hookspec
    async def on_answer_scored(
        self, session_id: str, question_id: str, score: float, feedback: str
    ):
        """Fired after an answer has been scored."""

    @hookspec(firstresult=True)
    async def on_difficulty_adjust(
        self, session_id: str, running_avg_score: float
    ) -> str | None:
        """Determine the next difficulty level.

        firstresult=True means the first non-None result wins.
        Return None to keep current difficulty.
        """

    @hookspec
    async def on_interview_end(self, session_id: str, final_report: dict):
        """Fired when the interview completes and report is generated."""

    @hookspec
    async def on_error(self, session_id: str, error: Exception, context: dict):
        """Fired on any error during interview processing."""

    @hookspec
    async def on_input_blocked(
        self,
        session_id: str,
        risk_type: str,
        reason: str,
        risk_score: float,
        input_preview: str,
    ):
        """Fired when input guard blocks a user's answer."""

    @hookspec
    async def on_output_sanitized(
        self,
        session_id: str,
        risk_type: str,
        reason: str,
        masked_count: int,
    ):
        """Fired when output guard sanitizes generated content."""
