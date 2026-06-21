"""Scoring service — evaluates answers and generates final reports."""
import json
import logging
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from server.models.question import Question
from server.models.answer import Answer
from server.models.interview import InterviewSession
from server.models.resume import Resume
from server.ai.llm import LLMFactory
from server.schemas.score import (
    ScoreReport,
    QuestionScore,
    ImprovementSuggestion,
)

logger = logging.getLogger(__name__)


class ScoringService:
    """Handles answer scoring and final report generation."""

    def __init__(self, llm_factory: LLMFactory):
        self.llm_factory = llm_factory

    async def generate_report(
        self, db: AsyncSession, session_id: str
    ) -> ScoreReport:
        """Generate a comprehensive interview report.

        Args:
            db: Database session.
            session_id: The interview session ID.

        Returns:
            A ScoreReport with all scores and suggestions.
        """
        # Fetch session
        result = await db.execute(
            select(InterviewSession).where(InterviewSession.id == session_id)
        )
        session = result.scalar_one_or_none()
        if not session:
            raise ValueError(f"Session {session_id} not found")

        # Fetch resume
        result = await db.execute(
            select(Resume).where(Resume.id == session.resume_id)
        )
        resume = result.scalar_one_or_none()

        # Fetch all questions with answers
        result = await db.execute(
            select(Question)
            .where(Question.session_id == session_id)
            .order_by(Question.order_index)
        )
        questions = list(result.scalars().all())

        # Build question scores
        question_scores = []
        total_score = 0.0
        scored_count = 0

        for q in questions:
            qs = QuestionScore(
                question_id=q.id,
                question_text=q.question_text,
                question_type=q.question_type,
                skill_module=q.skill_module,
                user_answer="",
            )

            # Fetch answer
            result = await db.execute(
                select(Answer).where(Answer.question_id == q.id)
            )
            answer = result.scalar_one_or_none()
            if answer:
                qs.user_answer = answer.user_answer
                qs.score = float(answer.score) if answer.score is not None else None
                qs.score_breakdown = answer.score_breakdown
                qs.feedback = answer.feedback

                if answer.score is not None:
                    total_score += float(answer.score)
                    scored_count += 1

            question_scores.append(qs)

        # Calculate overall
        overall = round(total_score / scored_count, 1) if scored_count > 0 else None

        # Aggregate by skill module
        skill_scores = {}
        for qs in question_scores:
            if qs.score is not None:
                module = qs.skill_module
                if module not in skill_scores:
                    skill_scores[module] = []
                skill_scores[module].append(qs.score)

        skill_breakdown = {
            k: round(sum(v) / len(v), 1) for k, v in skill_scores.items()
        }

        # Aggregate by dimension — dynamic: collect ALL dimension keys from answers
        dim_scores: dict[str, list] = {}
        for qs in question_scores:
            logger.warning(
                f"SCORING_DEBUG q_id={qs.question_id} "
                f"skill={qs.skill_module} "
                f"breakdown={qs.score_breakdown}"
            )
            if qs.score_breakdown:
                for dim_key, dim_val in qs.score_breakdown.items():
                    if dim_val is not None:
                        dim_scores.setdefault(dim_key, []).append(float(dim_val))

        # Build dimension breakdown with all collected dimensions
        dimension_breakdown = {}
        for k, v in dim_scores.items():
            if v:
                dimension_breakdown[k] = round(sum(v) / len(v), 1)

        logger.warning(
            f"SCORING_DEBUG session={session_id} "
            f"dim_scores={dict(dim_scores)} "
            f"dimension_breakdown={dimension_breakdown}"
        )

        # If no dimensions found at all, return None so frontend can show "暂无数据"
        if not dimension_breakdown:
            dimension_breakdown = None

        # Generate improvement suggestions via LLM
        suggestions = await self._generate_suggestions(
            question_scores,
            resume.tech_stack if resume else [],
            resume.years_experience if resume else None,
            session_id=session_id,
        )

        return ScoreReport(
            session_id=session_id,
            overall_score=overall,
            total_questions=len(questions),
            evaluated_questions=scored_count,
            dimension_breakdown=dimension_breakdown,
            skill_breakdown=skill_breakdown,
            questions=question_scores,
            improvement_suggestions=suggestions,
        )

    async def _generate_suggestions(
        self,
        question_scores: list[QuestionScore],
        tech_stack: list,
        years_experience: Optional[int],
        session_id: str = "",
    ) -> list[ImprovementSuggestion]:
        """Use LLM to generate improvement suggestions."""
        scores_text = "\n".join([
            f"Q: {qs.question_text[:100]}\nScore: {qs.score}\nFeedback: {qs.feedback or 'N/A'}\n"
            for qs in question_scores
        ])

        # Set trace context for observability
        try:
            from server.observability.callbacks import TraceContext
            TraceContext.set(session_id=session_id, phase="scoring")
        except Exception:
            pass
        try:
            llm = self.llm_factory.get_chat_model(temperature=0.4, max_tokens=1000)
            prompt = f"""根据以下面试表现，给出3-5条改进建议：

技术栈：{', '.join([t.get('name', '') for t in tech_stack])}
工作经验：{years_experience or '未知'} 年

各题表现：
{scores_text}

请输出 JSON 数组，每项包含 area（改进领域）、suggestion（建议内容）、priority（high/medium/low）。
只输出 JSON 数组，不要加其他内容。

示例：
[{{"area": "系统设计", "suggestion": "建议...", "priority": "high"}}]"""

            result = await llm.ainvoke(prompt)
        finally:
            try:
                TraceContext.clear()
            except Exception:
                pass
        try:
            raw = json.loads(result.content.strip())
            return [
                ImprovementSuggestion(
                    area=item.get("area", ""),
                    suggestion=item.get("suggestion", ""),
                    priority=item.get("priority", "medium"),
                )
                for item in raw
            ]
        except json.JSONDecodeError:
            return [
                ImprovementSuggestion(
                    area="综合",
                    suggestion="建议回顾面试中的薄弱环节，针对性地学习和练习",
                    priority="medium",
                )
            ]


# Singleton accessor
_scoring_service: Optional[ScoringService] = None


def get_scoring_service(llm_factory: LLMFactory) -> ScoringService:
    global _scoring_service
    if _scoring_service is None:
        _scoring_service = ScoringService(llm_factory)
    return _scoring_service
