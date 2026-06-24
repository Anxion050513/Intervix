"""Interview orchestrator — state machine + Agent hybrid driving the interview flow.

Session state is stored in-memory (L1) for low-latency access and persisted
to Redis (L2) for durability across server restarts.  The Redis layer also
provides TTL-based auto-expiry, cache-penetration markers, and jittered TTL
to avoid avalanche expiry.
"""
from __future__ import annotations

import asyncio
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

# Lazy import — Redis may not be available
try:
    from server.services.session_cache import SessionCache as _SessionCache
except Exception:
    _SessionCache = None


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


def _stream_chunks(text: str, max_chars: int = 5) -> list[str]:
    """Split *text* into word-level chunks for natural SSE streaming.

    Uses jieba for Chinese text when available; falls back to
    sentence/phrase-level splitting on punctuation boundaries.
    """
    if not text:
        return []

    try:
        import jieba as _jieba
        words = list(_jieba.cut(text))
        # Group short words together so chunks are readable but still small
        chunks: list[str] = []
        buf = ""
        for w in words:
            w = w or ""
            if len(buf) + len(w) <= max_chars:
                buf += w
            else:
                if buf:
                    chunks.append(buf)
                buf = w
        if buf:
            chunks.append(buf)
        return chunks
    except Exception:
        pass

    # Fallback: split on Chinese/English punctuation and whitespace boundaries
    import re as _re
    # Keep punctuation attached to preceding text for natural pauses
    parts = _re.split(r'(\s+|(?<=[。！？；，、：\n])|(?=[。！？；，、：\n]))', text)
    chunks = []
    buf = ""
    for part in parts:
        if not part or part.isspace():
            if buf:
                chunks.append(buf)
                buf = ""
            continue
        if len(buf) + len(part) <= max_chars * 2:
            buf += part
        else:
            if buf:
                chunks.append(buf)
            buf = part
    if buf:
        chunks.append(buf)
    return chunks or [text]


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
        self._cache: _SessionCache | None = None  # lazy-init on first use

    async def _get_cache(self):
        """Lazy-init the Redis session cache (non-blocking on first access)."""
        if self._cache is None and _SessionCache is not None:
            try:
                self._cache = await _SessionCache.create()
            except Exception as exc:
                logger.warning("SessionCache init failed, using memory-only: %s", exc)
                self._cache = None
        return self._cache

    # ── Redis persistence helpers ───────────────────────────────────

    @staticmethod
    def _serialize_ctx(ctx: SkillContext) -> dict:
        """Serialize SkillContext to a JSON-safe dict."""
        return {
            "tech_stack": [
                t if isinstance(t, str) else dict(t) for t in (ctx.tech_stack or [])
            ],
            "years_experience": ctx.years_experience,
            "difficulty": ctx.difficulty,
            "question_count": ctx.question_count,
            "session_id": ctx.session_id,
        }

    @staticmethod
    def _serialize_decision(d: AgentDecision | None) -> dict | None:
        """Serialize AgentDecision to a JSON-safe dict."""
        if d is None:
            return None
        return {
            "action": d.action.value,
            "reason": d.reason,
            "next_skill": d.next_skill,
            "new_difficulty": d.new_difficulty,
            "focus_topics": d.focus_topics,
            "follow_up_context": d.follow_up_context,
        }

    @staticmethod
    def _serialize_genq(gq: GeneratedQuestion | None) -> dict | None:
        """Serialize GeneratedQuestion to a JSON-safe dict."""
        if gq is None:
            return None
        return {
            "text": gq.text,
            "question_type": gq.question_type,
            "expected_topics": gq.expected_topics,
            "reference_answer": gq.reference_answer,
            "metadata": gq.metadata,
        }

    async def _save_session(self, session_id: str):
        """Persist the current in-memory session to Redis (write-through)."""
        if session_id not in self._active_sessions:
            return
        cache = await self._get_cache()
        if cache is None or not cache.enabled:
            return

        sd = self._active_sessions[session_id]
        payload = {
            "state": sd.get("state", ""),
            "current_skill": sd.get("current_skill"),
            "module_question_counts": sd.get("module_question_counts", {}),
            "module_scores": sd.get("module_scores", {}),
            "question_history": sd.get("question_history", []),
            "total_answers": sd.get("total_answers", 0),
            "_question_seq": sd.get("_question_seq", 0),
            "ctx": self._serialize_ctx(sd.get("ctx")),  # type: ignore[arg-type]
            "pending_agent_decision": self._serialize_decision(
                sd.get("pending_agent_decision")
            ),
            "pending_follow_up": sd.get("pending_follow_up"),
        }
        # Fire-and-forget — don't block the interview flow on Redis latency
        asyncio.create_task(cache.set(session_id, payload))

    async def _load_session(self, session_id: str) -> dict | None:
        """Try to restore session data from Redis (L2 cache miss fallback)."""
        cache = await self._get_cache()
        if cache is None or not cache.enabled:
            return None
        return await cache.get(session_id)

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

        # Persist initial session state to Redis
        await self._save_session(session.id)

        # ── Pre-warmup: generate first question immediately ──────────
        # This eliminates the LLM generation delay on the first SSE request,
        # giving a <200ms first-token experience for the user.
        try:
            warmup_skill = skill_registry.get("warmup")
            if warmup_skill:
                _set_trace(session_id=session.id, skill_module="warmup", phase="pre_warm")
                try:
                    pre_gen = await warmup_skill.generate_question(ctx)
                    # Store question in DB so it is available for the answer flow
                    question = Question(
                        session_id=session.id,
                        skill_module="warmup",
                        question_text=pre_gen.text,
                        question_type=pre_gen.question_type,
                        expected_topics=pre_gen.expected_topics,
                        reference_answer=pre_gen.reference_answer,
                        difficulty=ctx.difficulty,
                        order_index=0,
                        extra_data=pre_gen.metadata,
                    )
                    # NOTE: db_session is not available here (start_session
                    # receives the InterviewSession model, not the DB session).
                    # We store the pre-warmed question in the session dict; the
                    # first stream_question() call will persist it properly.
                    sd = self._active_sessions.get(session.id)
                    if sd:
                        sd["_pre_warmed_question"] = pre_gen
                        sd["_pre_warmed_question_obj"] = question
                        sd["_pre_warmed"] = True
                    logger.info("Pre-warmed warmup question for session %s", session.id)
                finally:
                    _clear_trace()
        except Exception as exc:
            logger.warning("Pre-warmup failed for session %s: %s", session.id, exc)
            sd = self._active_sessions.get(session.id)
            if sd:
                sd.pop("_pre_warmed_question", None)
                sd.pop("_pre_warmed_question_obj", None)

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

        # Warmup is counted separately (max 2, not part of question_count)
        warmup_count = module_counts.get("warmup", 0)
        warmup_max = 1
        total_answers = session_data.get("total_answers", 0)
        # Non-warmup modules for agent decision
        non_warmup_modules = [m for m in skill_modules if m != "warmup"]
        # Total asked excluding warmup (warmup doesn't count toward limit)
        non_warmup_asked = max(0, total_answers - warmup_count)

        _set_trace(session_id=session_id, phase="decide")
        try:
            return await self.agent.decide(
                session_id=session_id,
                tech_stack=ctx.tech_stack,
                years_experience=ctx.years_experience,
                difficulty=ctx.difficulty,
                current_skill=current_skill,
                skill_modules=non_warmup_modules,
                total_asked=non_warmup_asked,
                max_questions=ctx.question_count,
                module_count=module_counts.get(current_skill, 0),
                module_counts=module_counts,
                recent_history=history,
                module_scores=module_score_avgs,
                warmup_count=warmup_count,
                warmup_max=warmup_max,
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
            # Try Redis fallback (server restart)
            session_data = await self.get_session_data(session.id)
        if not session_data:
            return None, InterviewState.COMPLETE

        ctx: SkillContext = session_data["ctx"]
        current_state: str = session_data["state"]
        skill_modules = session.skill_modules or ["warmup", "technical_qa", "behavioral"]
        max_questions = ctx.question_count

        # --- Check if we're done ---
        if session.question_count >= max_questions:
            session_data["state"] = InterviewState.SCORING
            await self._save_session(session.id)
            return None, InterviewState.SCORING

        # --- First question: always go to WARMUP (ice-breaker) ---
        if current_state == InterviewState.IDLE:
            next_state = InterviewState.WARMUP
            skill_name = "warmup"
            session_data["state"] = next_state
            session_data["current_skill"] = skill_name
            result = await self._generate_with_skill(
                session, db_session, session_data, skill_name, next_state
            )
            await self._save_session(session.id)
            return result

        # --- Agent-driven decision (only after at least one answer) ---
        has_history = len(session_data.get("question_history", [])) > 0
        if self.agent.enabled and has_history:
            decision = await self._consult_agent(session.id, session_data, skill_modules)
            session_data["pending_agent_decision"] = decision
            result = await self._enact_agent_decision(
                session, db_session, session_data, decision, skill_modules
            )
            await self._save_session(session.id)
            return result

        # --- Fallback: state machine ---
        result = await self._state_machine_next(session, db_session, session_data, skill_modules)
        await self._save_session(session.id)
        return result

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

        # ── Enforce per-module question limits ──────────────────────
        # The agent may suggest CONTINUE/FOLLOW_UP on a module that has
        # already reached its max. Override to switch_skill in that case.
        skill = skill_registry.get(current_skill)
        if skill is not None:
            module_counts = session_data.get("module_question_counts", {})
            asked_in_module = module_counts.get(current_skill, 0)
            if asked_in_module >= skill.max_questions:
                # Force switch — module has reached its cap
                try:
                    idx = skill_modules.index(current_skill)
                    next_skill = skill_modules[idx + 1] if idx + 1 < len(skill_modules) else None
                except (ValueError, IndexError):
                    next_skill = None
                if next_skill:
                    logger.info(
                        "Module '%s' cap reached (%d/%d), forcing switch to '%s'",
                        current_skill, asked_in_module, skill.max_questions, next_skill,
                    )
                    decision = AgentDecision(
                        action=AgentAction.SWITCH_SKILL,
                        reason=f"模块{current_skill}已达上限{skill.max_questions}题，强制切换",
                        next_skill=next_skill,
                    )
                else:
                    # No more modules, end interview
                    session_data["state"] = InterviewState.SCORING
                    return None, InterviewState.SCORING

        if decision.action == AgentAction.FOLLOW_UP:
            # Stay in same skill, agent provides focus context
            skill = skill_registry.get(current_skill)
            if skill:
                # Store follow-up context in session_data so _generate_with_skill
                # can inject it AFTER syncing real Q&A history (avoids overwrite).
                if decision.follow_up_context:
                    session_data["pending_follow_up"] = {
                        "type": "follow_up_hint",
                        "context": decision.follow_up_context,
                        "topics": decision.focus_topics,
                    }
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

        # Sync real Q&A history into skill context (Bug 1 fix)
        ctx.session_history = list(session_data.get("question_history", []))
        # Inject pending follow-up context from agent decision (Bug 2 fix)
        pending_follow_up = session_data.pop("pending_follow_up", None)
        if pending_follow_up:
            ctx.session_history.append(pending_follow_up)

        # Generate question (traced)
        _set_trace(session_id=session.id, skill_module=skill_name, phase="generate")
        try:
            gen_q = await skill.generate_question(ctx)
        finally:
            _clear_trace()
        module_counts = session_data["module_question_counts"]
        module_counts[skill_name] = module_counts.get(skill_name, 0) + 1
        session_data["module_question_counts"] = module_counts

        # Create Question in DB (use running sequence for ordering, not question_count)
        seq_index = session_data.setdefault("_question_seq", 0)
        question = Question(
            session_id=session.id,
            skill_module=skill_name,
            question_text=gen_q.text,
            question_type=gen_q.question_type,
            expected_topics=gen_q.expected_topics,
            reference_answer=gen_q.reference_answer,
            difficulty=ctx.difficulty,
            order_index=seq_index,
            extra_data=gen_q.metadata,
        )
        db_session.add(question)
        await db_session.flush()
        session_data["_question_seq"] = seq_index + 1

        # Update session counter (warmup doesn't count toward total)
        if skill_name != "warmup":
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
            # Try Redis fallback (server restart during interview)
            session_data = await self.get_session_data(session.id)
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
            # Record blocked answer in history too, so the LLM can see what happened
            session_data["question_history"].append({
                "question": gen_q.text,
                "answer": f"[输入被安全护栏拦截: {guard_result.reason}]",
                "score": 0,
                "skill": current_skill,
            })
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

        # Track per-module scores (warmup scores are None but we still need to
        # count them so the agent knows the module was visited)
        if current_skill:
            module_scores = session_data.setdefault("module_scores", {})
            if current_skill not in module_scores:
                module_scores[current_skill] = []
            s = score_data.get("score")
            # Use actual score if present, otherwise use score_breakdown avg as proxy
            if s is not None:
                module_scores[current_skill].append(s)
            elif score_data.get("score_breakdown"):
                breakdown = score_data["score_breakdown"]
                if breakdown:
                    proxy = sum(breakdown.values()) / len(breakdown)
                    module_scores[current_skill].append(proxy)

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

        # Persist updated session to Redis
        await self._save_session(session.id)

        return answer

    async def stream_question(
        self, session: InterviewSession, db_session
    ) -> AsyncGenerator[str, None]:
        """Stream a question token-by-token via SSE with word-level chunking.

        Uses jieba for Chinese word segmentation to produce natural reading
        rhythm, falling back to sentence-level chunking when jieba is unavailable.
        The rephrase LLM call has been eliminated — the generated question text
        is streamed directly, reducing first-token latency.
        """
        import asyncio as _asyncio

        # Check for pre-warmed question first
        session_data = self._active_sessions.get(session.id)
        if not session_data:
            session_data = await self.get_session_data(session.id)
        if not session_data:
            yield f"data: {json.dumps({'type': 'error', 'message': 'session not found'})}\n\n"
            return

        pre_warmed: GeneratedQuestion | None = session_data.pop("_pre_warmed_question", None)
        pre_warmed_db: Question | None = session_data.pop("_pre_warmed_question_obj", None)
        if pre_warmed is not None:
            gen_q = pre_warmed
            state = InterviewState.WARMUP
            session_data["state"] = InterviewState.WARMUP
            session_data["current_skill"] = "warmup"

            # Persist the pre-warmed question to DB now that we have a session
            if pre_warmed_db is not None:
                db_session.add(pre_warmed_db)
                await db_session.flush()
                session_data["current_question"] = pre_warmed_db
                session_data["current_gen_q"] = gen_q
                session_data["module_question_counts"]["warmup"] = \
                    session_data["module_question_counts"].get("warmup", 0) + 1
                session_data["_question_seq"] = 1

            await self._save_session(session.id)
            logger.info("Using pre-warmed question for session %s", session.id)
        else:
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

        # Refresh session_data after next_question may have created/updated it
        session_data = self._active_sessions.get(session.id)
        if not session_data:
            session_data = await self.get_session_data(session.id)

        meta = {
            "type": "question_meta",
            "question_id": getattr(
                session_data.get("current_question", {}),
                "id", ""
            ) if session_data else "",
            "question_type": gen_q.question_type,
            "skill_module": session_data.get("current_skill", "") if session_data else state,
            "difficulty": session_data["ctx"].difficulty if session_data else "medium",
        }
        yield f"data: {json.dumps(meta)}\n\n"

        # Stream word-by-word (jieba) or sentence-by-sentence (fallback)
        # No rephrase LLM call — stream the original question text directly.
        for chunk in _stream_chunks(safe_text):
            safe_chunk = self.output_guard.validate_streaming_chunk(chunk)
            if safe_chunk:
                yield f"data: {json.dumps({'type': 'token', 'content': safe_chunk})}\n\n"
                await _asyncio.sleep(0.08)  # natural reading pace

        yield f"data: {json.dumps({'type': 'question_complete'})}\n\n"

    async def get_session_data(self, session_id: str) -> dict | None:
        """Get session data — Redis as primary source, memory as fast cache.

        Every call hits Redis first for freshness, then syncs the memory
        cache.  This means Redis is actively used during normal operation,
        not just on server restart.
        """
        # Try Redis first (primary store)
        raw = await self._load_session(session_id)
        if raw is not None:
            # Rebuild or update in-memory cache from Redis
            self._active_sessions[session_id] = await self._restore_from_redis(session_id, raw)
            return self._active_sessions[session_id]

        # Redis miss — check memory (may have data from before Redis was enabled)
        if session_id in self._active_sessions:
            return self._active_sessions[session_id]

        # Mark non-existent to prevent repeated cache penetration
        cache = await self._get_cache()
        if cache is not None and cache.enabled:
            asyncio.create_task(cache.mark_empty(session_id))
        return None

    async def _restore_from_redis(self, session_id: str, raw: dict) -> dict:
        """Rebuild in-memory session context from a Redis payload."""
        ctx_data = raw.get("ctx", {})
        ctx = SkillContext(
            tech_stack=ctx_data.get("tech_stack", []),
            years_experience=ctx_data.get("years_experience"),
            difficulty=ctx_data.get("difficulty", "medium"),
            session_id=session_id,
            question_count=ctx_data.get("question_count", 10),
        )
        ctx.session_history = list(raw.get("question_history", []))

        pending_decision = None
        pd_raw = raw.get("pending_agent_decision")
        if pd_raw:
            try:
                pending_decision = AgentDecision(
                    action=AgentAction(pd_raw["action"]),
                    reason=pd_raw.get("reason", ""),
                    next_skill=pd_raw.get("next_skill"),
                    new_difficulty=pd_raw.get("new_difficulty"),
                    focus_topics=pd_raw.get("focus_topics", []),
                    follow_up_context=pd_raw.get("follow_up_context"),
                )
            except (ValueError, KeyError):
                pass

        session_data = {
            "state": raw.get("state", InterviewState.IDLE),
            "ctx": ctx,
            "question_history": raw.get("question_history", []),
            "module_question_counts": raw.get("module_question_counts", {}),
            "module_scores": raw.get("module_scores", {}),
            "current_skill": raw.get("current_skill"),
            "pending_agent_decision": pending_decision,
            "pending_follow_up": raw.get("pending_follow_up"),
            "total_answers": raw.get("total_answers", 0),
            "_question_seq": raw.get("_question_seq", 0),
            "_restored_from_redis": True,
        }
        logger.info("Session %s loaded from Redis", session_id)
        return session_data

        # Rebuild in-memory context from Redis payload
        ctx_data = raw.get("ctx", {})
        ctx = SkillContext(
            tech_stack=ctx_data.get("tech_stack", []),
            years_experience=ctx_data.get("years_experience"),
            difficulty=ctx_data.get("difficulty", "medium"),
            session_id=session_id,
            question_count=ctx_data.get("question_count", 10),
        )
        # Restore session history into ctx
        ctx.session_history = list(raw.get("question_history", []))

        # Rebuild AgentDecision if stored
        pending_decision = None
        pd_raw = raw.get("pending_agent_decision")
        if pd_raw:
            try:
                pending_decision = AgentDecision(
                    action=AgentAction(pd_raw["action"]),
                    reason=pd_raw.get("reason", ""),
                    next_skill=pd_raw.get("next_skill"),
                    new_difficulty=pd_raw.get("new_difficulty"),
                    focus_topics=pd_raw.get("focus_topics", []),
                    follow_up_context=pd_raw.get("follow_up_context"),
                )
            except (ValueError, KeyError):
                pass

        session_data = {
            "state": raw.get("state", InterviewState.IDLE),
            "ctx": ctx,
            "question_history": raw.get("question_history", []),
            "module_question_counts": raw.get("module_question_counts", {}),
            "module_scores": raw.get("module_scores", {}),
            "current_skill": raw.get("current_skill"),
            "pending_agent_decision": pending_decision,
            "pending_follow_up": raw.get("pending_follow_up"),
            "total_answers": raw.get("total_answers", 0),
            "_question_seq": raw.get("_question_seq", 0),
            "_restored_from_redis": True,
        }
        self._active_sessions[session_id] = session_data
        logger.info("Session %s restored from Redis", session_id)
        return session_data

    async def end_session(self, session: InterviewSession, db_session) -> dict:
        """End the interview and trigger scoring."""
        session_data = self._active_sessions.get(session.id)
        if not session_data:
            session_data = await self.get_session_data(session.id)
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

        # Clean up Redis session
        cache = await self._get_cache()
        if cache is not None and cache.enabled:
            await cache.delete(session.id)

        return {"status": "completed", "total_questions": session.question_count}


# Global singleton
_orchestrator: InterviewOrchestrator | None = None


def get_orchestrator(llm_factory: LLMFactory, agent_enabled: bool = True) -> InterviewOrchestrator:
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = InterviewOrchestrator(llm_factory, agent_enabled=agent_enabled)
    return _orchestrator
