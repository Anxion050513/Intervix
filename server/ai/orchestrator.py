"""Interview orchestrator — state machine + Agent hybrid driving the interview flow."""
import json
import logging
from typing import AsyncGenerator

from server.ai.skills.base import SkillContext, GeneratedQuestion
from server.ai.skills.registry import skill_registry
from server.ai.llm import LLMFactory
from server.ai.agent.decision_agent import InterviewAgent, AgentDecision, AgentAction
from server.ai.guardrails.input_guard import InputGuard, InputGuardResult, InputRisk
from server.ai.guardrails.output_guard import OutputGuard, OutputGuardResult
from server.harness.manager import harness
from server.models.question import Question
from server.models.answer import Answer
from server.models.interview import InterviewSession

logger = logging.getLogger(__name__)

# Lazy import — observability module may not be installed
try:
    from server.observability.callbacks import TraceContext as _TraceContext
except Exception:
    _TraceContext = None


def _set_trace(*, session_id="", skill_module="", question_id="", phase=""):
    """Set trace context if observability is available."""
    if _TraceContext:
        _TraceContext.set(
            session_id=session_id,
            skill_module=skill_module,
            question_id=question_id,
            phase=phase,
        )


def _clear_trace():
    """Clear trace context if observability is available."""
    if _TraceContext:
        _TraceContext.clear()


class InterviewState:
    IDLE = "idle"
    WARMUP = "warmup"
    TECHNICAL_QA = "technical_qa"
    BEHAVIORAL = "behavioral"
    SYSTEM_DESIGN = "system_design"
    CODING = "coding_challenge"
    SCORING = "scoring"
    COMPLETE = "complete"


# State transition: which skill runs in each state
STATE_TO_SKILL = {
    InterviewState.WARMUP: "warmup",
    InterviewState.TECHNICAL_QA: "technical_qa",
    InterviewState.BEHAVIORAL: "behavioral",
    InterviewState.SYSTEM_DESIGN: "system_design",
    InterviewState.CODING: "coding_challenge",
}

# Order of states
STATE_ORDER = [
    InterviewState.WARMUP,
    InterviewState.TECHNICAL_QA,
    InterviewState.BEHAVIORAL,
    InterviewState.SYSTEM_DESIGN,
    InterviewState.CODING,
]


class InterviewOrchestrator:
    """Hybrid orchestrator: state machine skeleton + LLM Agent for dynamic decisions.

    The state machine provides the overall flow structure.
    The Agent decides when to follow up, skip, switch, or adjust difficulty
    based on the candidate's actual performance.
    """

    def __init__(self, llm_factory: LLMFactory, agent_enabled: bool = True):
        self.llm_factory = llm_factory
        self.agent = InterviewAgent(llm_factory, enabled=agent_enabled)
        self.input_guard = InputGuard(llm_factory=llm_factory, llm_enabled=True)
        self.output_guard = OutputGuard()
        self._active_sessions: dict[str, dict] = {}

    def _get_next_state(self, current_state: str, skill_modules: list[str]) -> str:
        """Determine the next state in the interview flow (state machine fallback)."""
        if current_state == InterviewState.IDLE:
            return InterviewState.WARMUP

        try:
            idx = STATE_ORDER.index(current_state)
            next_idx = idx + 1
        except ValueError:
            return InterviewState.SCORING

        if next_idx >= len(STATE_ORDER):
            return InterviewState.SCORING

        next_state = STATE_ORDER[next_idx]
        skill_name = STATE_TO_SKILL.get(next_state, "")
        if skill_name in skill_modules:
            return next_state

        return self._get_next_state(next_state, skill_modules)

    def _state_for_skill(self, skill_name: str) -> str:
        """Reverse lookup: given a skill name, return the state."""
        for state, name in STATE_TO_SKILL.items():
            if name == skill_name:
                return state
        return InterviewState.SCORING

    async def start_session(
        self,
        session: InterviewSession,
        resume_data: dict,
        tech_stack: list,
        years_experience: int | None,
    ) -> SkillContext:
        """Initialize a new interview session."""
        skill_modules = session.skill_modules or ["warmup", "technical_qa", "behavioral"]

        ctx = SkillContext(
            resume_data=resume_data,
            tech_stack=tech_stack,
            years_experience=years_experience,
            difficulty=session.difficulty_level,
            session_id=session.id,
            question_count=session.settings.get("question_count", 10),
        )

        self._active_sessions[session.id] = {
            "state": InterviewState.IDLE,
            "ctx": ctx,
            "question_history": [],
            "module_question_counts": {},
            "module_scores": {},       # skill_name -> list of scores
            "current_skill": None,      # Currently active skill name
            "pending_agent_decision": None,  # Agent decision awaiting enactment
        }

        await harness.fire(
            "on_interview_start",
            session_id=session.id,
            resume_data=resume_data,
            skill_modules=skill_modules,
        )

        for skill_name in skill_modules:
            skill = skill_registry.get(skill_name)
            if skill:
                await skill.on_session_start(ctx)

        return ctx

    async def _consult_agent(
        self, session_id: str, session_data: dict, skill_modules: list[str]
    ) -> AgentDecision:
        """Ask the agent what to do next based on current interview state."""
        ctx: SkillContext = session_data["ctx"]
        current_skill = session_data.get("current_skill") or skill_modules[0]
        history: list[dict] = session_data["question_history"]
        module_counts: dict = session_data["module_question_counts"]
        module_scores_raw: dict[str, list] = session_data.get("module_scores", {})

        # Calculate average scores per module
        module_score_avgs = {}
        for mod, scores in module_scores_raw.items():
            if scores:
                module_score_avgs[mod] = sum(scores) / len(scores)

        _set_trace(session_id=session_id, phase="decide")
        try:
            return await self.agent.decide(
                session_id=session_id,
                tech_stack=ctx.tech_stack,
                years_experience=ctx.years_experience,
                difficulty=ctx.difficulty,
                current_skill=current_skill,
                skill_modules=skill_modules,
                total_asked=session_data.get("total_answers", 0),
                max_questions=ctx.question_count,
                module_count=module_counts.get(current_skill, 0),
                recent_history=history,
                module_scores=module_score_avgs,
            )
        finally:
            _clear_trace()

    async def next_question(
        self, session: InterviewSession, db_session
    ) -> tuple[GeneratedQuestion | None, str]:
        """Generate the next question — Agent-driven or state machine fallback.

        Returns:
            Tuple of (GeneratedQuestion, new_state) or (None, "scoring") if done.
        """
        session_data = self._active_sessions.get(session.id)
        if not session_data:
            return None, InterviewState.COMPLETE

        ctx: SkillContext = session_data["ctx"]
        current_state: str = session_data["state"]
        skill_modules = session.skill_modules or ["warmup", "technical_qa", "behavioral"]
        max_questions = ctx.question_count

        # --- Check if we're done ---
        if session.question_count >= max_questions:
            session_data["state"] = InterviewState.SCORING
            return None, InterviewState.SCORING

        # --- First question: always go to WARMUP (ice-breaker) ---
        if current_state == InterviewState.IDLE:
            next_state = InterviewState.WARMUP
            skill_name = "warmup"
            session_data["state"] = next_state
            session_data["current_skill"] = skill_name
            return await self._generate_with_skill(
                session, db_session, session_data, skill_name, next_state
            )

        # --- Agent-driven decision (only after at least one answer) ---
        has_history = len(session_data.get("question_history", [])) > 0
        if self.agent.enabled and has_history:
            decision = await self._consult_agent(session.id, session_data, skill_modules)
            session_data["pending_agent_decision"] = decision
            return await self._enact_agent_decision(
                session, db_session, session_data, decision, skill_modules
            )

        # --- Fallback: state machine ---
        return await self._state_machine_next(session, db_session, session_data, skill_modules)

    async def _enact_agent_decision(
        self,
        session: InterviewSession,
        db_session,
        session_data: dict,
        decision: AgentDecision,
        skill_modules: list[str],
    ) -> tuple[GeneratedQuestion | None, str]:
        """Execute the agent's decision."""
        ctx: SkillContext = session_data["ctx"]
        current_skill = session_data.get("current_skill") or skill_modules[0]
        state = session_data["state"]

        if decision.action == AgentAction.FOLLOW_UP:
            # Stay in same skill, agent provides focus context
            skill = skill_registry.get(current_skill)
            if skill:
                # Inject follow-up context into the skill context
                if decision.follow_up_context:
                    ctx.session_history.append({
                        "type": "follow_up_hint",
                        "context": decision.follow_up_context,
                        "topics": decision.focus_topics,
                    })
                return await self._generate_with_skill(
                    session, db_session, session_data, current_skill, state
                )
            else:
                return await self._state_machine_next(
                    session, db_session, session_data, skill_modules
                )

        elif decision.action == AgentAction.CONTINUE:
            return await self._generate_with_skill(
                session, db_session, session_data, current_skill, state
            )

        elif decision.action == AgentAction.SWITCH_SKILL:
            next_skill = decision.next_skill
            if not next_skill:
                # Find next skill in module list
                try:
                    idx = skill_modules.index(current_skill)
                    next_skill = skill_modules[idx + 1] if idx + 1 < len(skill_modules) else None
                except (ValueError, IndexError):
                    next_skill = None

            if next_skill and next_skill in skill_modules:
                new_state = self._state_for_skill(next_skill)
                session_data["state"] = new_state
                session_data["current_skill"] = next_skill
                if decision.new_difficulty:
                    ctx.difficulty = decision.new_difficulty
                return await self._generate_with_skill(
                    session, db_session, session_data, next_skill, new_state
                )
            else:
                # No more skills, go to scoring
                session_data["state"] = InterviewState.SCORING
                return None, InterviewState.SCORING

        elif decision.action == AgentAction.SKIP_SKILL:
            skip_target = decision.next_skill or current_skill
            logger.info(f"Agent decided to skip skill: {skip_target} — {decision.reason}")
            # Remove the skipped skill from consideration
            remaining = [s for s in skill_modules if s != skip_target]
            if not remaining:
                session_data["state"] = InterviewState.SCORING
                return None, InterviewState.SCORING
            session.skill_modules = remaining
            return await self._state_machine_next(
                session, db_session, session_data, remaining
            )

        elif decision.action == AgentAction.ADJUST_DIFFICULTY:
            if decision.new_difficulty:
                ctx.difficulty = decision.new_difficulty
                await harness.fire(
                    "on_difficulty_adjust",
                    session_id=session.id,
                    running_avg_score=0.0,
                )
            return await self._generate_with_skill(
                session, db_session, session_data, current_skill, state
            )

        elif decision.action == AgentAction.CONCLUDE:
            session_data["state"] = InterviewState.SCORING
            logger.info(f"Agent decided to conclude early: {decision.reason}")
            return None, InterviewState.SCORING

        # Default fallback
        return await self._state_machine_next(
            session, db_session, session_data, skill_modules
        )

    async def _state_machine_next(
        self,
        session: InterviewSession,
        db_session,
        session_data: dict,
        skill_modules: list[str],
    ) -> tuple[GeneratedQuestion | None, str]:
        """Traditional state-machine driven next question (fallback)."""
        ctx: SkillContext = session_data["ctx"]
        current_state: str = session_data["state"]
        max_questions = ctx.question_count

        if session.question_count >= max_questions:
            session_data["state"] = InterviewState.SCORING
            return None, InterviewState.SCORING

        next_state = self._get_next_state(current_state, skill_modules)
        session_data["state"] = next_state

        if next_state == InterviewState.SCORING:
            return None, InterviewState.SCORING

        skill_name = STATE_TO_SKILL.get(next_state)
        if not skill_name:
            return None, InterviewState.SCORING

        skill = skill_registry.get(skill_name)
        if not skill:
            logger.warning(f"Skill '{skill_name}' not registered, skipping")
            session_data["state"] = next_state
            return await self._state_machine_next(
                session, db_session, session_data, skill_modules
            )

        module_counts = session_data["module_question_counts"]
        module_count = module_counts.get(skill_name, 0)
        if module_count >= skill.max_questions:
            session_data["state"] = next_state
            return await self._state_machine_next(
                session, db_session, session_data, skill_modules
            )

        session_data["current_skill"] = skill_name
        return await self._generate_with_skill(
            session, db_session, session_data, skill_name, next_state
        )

    async def _generate_with_skill(
        self,
        session: InterviewSession,
        db_session,
        session_data: dict,
        skill_name: str,
        state: str,
    ) -> tuple[GeneratedQuestion | None, str]:
        """Generate a question using the given skill module."""
        ctx: SkillContext = session_data["ctx"]
        skill = skill_registry.get(skill_name)
        if not skill:
            return None, InterviewState.SCORING

        # Generate question (traced)
        _set_trace(session_id=session.id, skill_module=skill_name, phase="generate")
        try:
            gen_q = await skill.generate_question(ctx)
        finally:
            _clear_trace()
        module_counts = session_data["module_question_counts"]
        module_counts[skill_name] = module_counts.get(skill_name, 0) + 1
        session_data["module_question_counts"] = module_counts

        # Create Question in DB
        question = Question(
            session_id=session.id,
            skill_module=skill_name,
            question_text=gen_q.text,
            question_type=gen_q.question_type,
            expected_topics=gen_q.expected_topics,
            reference_answer=gen_q.reference_answer,
            difficulty=ctx.difficulty,
            order_index=session.question_count,
            extra_data=gen_q.metadata,
        )
        db_session.add(question)
        await db_session.flush()

        # Update session counter
        session.question_count += 1
        session.current_question_index = session.question_count - 1
        await db_session.flush()

        session_data["current_question"] = question
        session_data["current_gen_q"] = gen_q

        await harness.fire(
            "on_question_generated",
            session_id=session.id,
            question_id=question.id,
            question_text=gen_q.text,
            question_type=gen_q.question_type,
            skill_name=skill_name,
            difficulty=ctx.difficulty,
            order_index=session.question_count - 1,
        )

        return gen_q, state

    async def submit_answer(
        self, session: InterviewSession, question_id: str, answer_text: str, db_session
    ) -> Answer | None:
        """Evaluate a user's answer and record results for agent observation.

        Guardrails: user input is checked for prompt injection, harmful content,
        and off-topic requests before evaluation.
        """
        session_data = self._active_sessions.get(session.id)
        if not session_data:
            return None

        ctx: SkillContext = session_data["ctx"]
        gen_q: GeneratedQuestion | None = session_data.get("current_gen_q")
        current_skill = session_data.get("current_skill", "")

        if not gen_q:
            return None

        # === Input Guard: check user answer for safety ===
        guard_result: InputGuardResult = await self.input_guard.check(answer_text)
        if not guard_result.is_safe:
            logger.warning(
                f"Input guard blocked answer in session {session.id}: "
                f"type={guard_result.risk_type}, score={guard_result.risk_score:.2f}"
            )
            await harness.fire(
                "on_input_blocked",
                session_id=session.id,
                risk_type=guard_result.risk_type.value,
                reason=guard_result.reason,
                risk_score=guard_result.risk_score,
                input_preview=answer_text[:300],
            )
            # Return a dummy answer with negative feedback instead of evaluating
            blocked_answer = Answer(
                question_id=question_id,
                user_answer="[输入已被安全护栏拦截]",
                score=0.0,
                score_breakdown={
                    "technical_accuracy": 0,
                    "depth_breadth": 0,
                    "clarity": 0,
                    "practical_experience": 0,
                },
                feedback=f"您的回答因安全原因未被接受：{guard_result.reason}。请重新回答与面试相关的内容。",
                is_evaluated=True,
            )
            db_session.add(blocked_answer)
            await db_session.flush()
            return blocked_answer

        # Use sanitized text for processing
        safe_answer = guard_result.sanitized_text

        await harness.fire(
            "on_answer_submitted",
            session_id=session.id,
            question_id=question_id,
            answer_text=safe_answer,
        )

        skill = skill_registry.get(current_skill)

        _set_trace(
            session_id=session.id,
            skill_module=current_skill,
            question_id=question_id,
            phase="evaluate",
        )
        try:
            if skill:
                score_data = await skill.evaluate_answer(gen_q, safe_answer, ctx)
            else:
                score_data = {"score": None, "score_breakdown": {}, "feedback": "无评分"}
        finally:
            _clear_trace()

        # Record in history (for agent observation)
        session_data["question_history"].append({
            "question": gen_q.text,
            "answer": safe_answer,
            "score": score_data.get("score"),
            "skill": current_skill,
        })

        # Track per-module scores
        if current_skill:
            module_scores = session_data.setdefault("module_scores", {})
            if current_skill not in module_scores:
                module_scores[current_skill] = []
            if score_data.get("score") is not None:
                module_scores[current_skill].append(score_data["score"])

        # Track total answers
        session_data["total_answers"] = session_data.get("total_answers", 0) + 1

        # Create Answer in DB
        answer = Answer(
            question_id=question_id,
            user_answer=safe_answer,
            score=score_data.get("score"),
            score_breakdown=score_data.get("score_breakdown", {}),
            feedback=score_data.get("feedback", ""),
            is_evaluated=True,
        )
        db_session.add(answer)
        await db_session.flush()

        if score_data.get("score") is not None:
            await harness.fire(
                "on_answer_scored",
                session_id=session.id,
                question_id=question_id,
                score=score_data["score"],
                feedback=score_data.get("feedback", ""),
            )

        # Difficulty adjustment (shared between agent and fallback)
        scores = [
            h["score"] for h in session_data["question_history"]
            if h.get("score") is not None
        ]
        if scores:
            avg = sum(scores) / len(scores)
            new_diff = await harness.fire(
                "on_difficulty_adjust",
                session_id=session.id,
                running_avg_score=avg,
            )
            if new_diff:
                ctx.difficulty = new_diff

        return answer

    async def stream_question(
        self, session: InterviewSession, db_session
    ) -> AsyncGenerator[str, None]:
        """Stream a question token-by-token via SSE.

        Output guard: generated question text and streamed chunks are checked
        for PII leakage and sensitive content before sending.
        """
        gen_q, state = await self.next_question(session, db_session)
        if gen_q is None:
            yield f"data: {json.dumps({'type': 'interview_complete', 'state': state})}\n\n"
            return

        # === Output Guard: check generated question for PII/sensitive content ===
        output_check: OutputGuardResult = self.output_guard.validate(gen_q.text)
        safe_text = output_check.sanitized_text if output_check.sanitized_text else gen_q.text

        if output_check.masked_items or not output_check.is_safe:
            await harness.fire(
                "on_output_sanitized",
                session_id=session.id,
                risk_type=output_check.risk_type.value,
                reason=output_check.reason,
                masked_count=len(output_check.masked_items),
            )

        import json as json_mod
        meta = {
            "type": "question_meta",
            "question_id": getattr(
                self._active_sessions[session.id].get("current_question", {}),
                "id", ""
            ),
            "question_type": gen_q.question_type,
            "skill_module": self._active_sessions[session.id].get("current_skill", ""),
            "difficulty": self._active_sessions[session.id]["ctx"].difficulty,
        }
        yield f"data: {json_mod.dumps(meta)}\n\n"

        _set_trace(session_id=session.id, phase="rephrase")
        try:
            llm = self.llm_factory.get_chat_model(streaming=True, temperature=0)
            prompt = f"请用友好的语气复述以下内容（保持内容不变，只改语气）：\n{safe_text}"
            async for chunk in llm.astream(prompt):
                if chunk.content:
                    # Per-chunk PII check (fast, regex only)
                    safe_chunk = self.output_guard.validate_streaming_chunk(chunk.content)
                    yield f"data: {json_mod.dumps({'type': 'token', 'content': safe_chunk})}\n\n"
        finally:
            _clear_trace()

        yield f"data: {json_mod.dumps({'type': 'question_complete'})}\n\n"

    def get_session_data(self, session_id: str) -> dict | None:
        return self._active_sessions.get(session_id)

    async def end_session(self, session: InterviewSession, db_session) -> dict:
        """End the interview and trigger scoring."""
        session_data = self._active_sessions.get(session.id)
        if not session_data:
            return {}

        session.status = "completed"
        await db_session.flush()

        await harness.fire(
            "on_interview_end",
            session_id=session.id,
            final_report={},
        )

        self.agent.reset_session(session.id)
        self._active_sessions.pop(session.id, None)
        return {"status": "completed", "total_questions": session.question_count}


# Global singleton
_orchestrator: InterviewOrchestrator | None = None


def get_orchestrator(llm_factory: LLMFactory, agent_enabled: bool = True) -> InterviewOrchestrator:
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = InterviewOrchestrator(llm_factory, agent_enabled=agent_enabled)
    return _orchestrator
