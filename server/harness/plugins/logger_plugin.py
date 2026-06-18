"""Logger plugin — logs all interview events to structured log."""
import logging
import json

from server.harness.hooks import InterviewHooks

logger = logging.getLogger("ai_interviewer.events")


class LoggerPlugin(InterviewHooks):
    """Logs every interview lifecycle event to a structured logger."""

    async def on_interview_start(self, session_id, resume_data, skill_modules):
        logger.info(
            f"INTERVIEW_START | session={session_id} | "
            f"skills={skill_modules}"
        )

    async def on_question_generated(
        self, session_id, question_id, question_text, question_type,
        skill_name, difficulty, order_index
    ):
        logger.info(
            f"QUESTION_GENERATED | session={session_id} | "
            f"q_id={question_id} | type={question_type} | "
            f"skill={skill_name} | difficulty={difficulty} | "
            f"order={order_index}"
        )

    async def on_answer_submitted(self, session_id, question_id, answer_text):
        logger.info(
            f"ANSWER_SUBMITTED | session={session_id} | "
            f"q_id={question_id} | len={len(answer_text)}"
        )

    async def on_answer_scored(self, session_id, question_id, score, feedback):
        logger.info(
            f"ANSWER_SCORED | session={session_id} | "
            f"q_id={question_id} | score={score}"
        )

    async def on_difficulty_adjust(self, session_id, running_avg_score):
        return None  # Let DifficultyAdjusterPlugin handle this

    async def on_interview_end(self, session_id, final_report):
        logger.info(
            f"INTERVIEW_END | session={session_id} | "
            f"score={final_report.get('overall_score', 'N/A')}"
        )

    async def on_error(self, session_id, error, context):
        logger.error(
            f"INTERVIEW_ERROR | session={session_id} | "
            f"error={error} | context={json.dumps(context, default=str)}"
        )
