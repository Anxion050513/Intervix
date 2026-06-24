"""Interview Agent — LLM-driven autonomous decision-making for interview flow.

This replaces the rigid state machine with an LLM-powered agent that decides:
- Whether to follow up on a weak answer (drill deeper)
- Whether to skip a skill area the candidate clearly excels at
- When to adjust difficulty
- What type of question to ask next

The agent uses a structured ReAct-style prompt to observe the interview state
and produce a decision, which the orchestrator then enacts.
"""
import json
import logging
from dataclasses import dataclass, field
from enum import StrEnum

from langchain_core.messages import HumanMessage, SystemMessage

from server.ai.llm import LLMFactory

logger = logging.getLogger(__name__)


class AgentAction(StrEnum):
    """Actions the agent can decide to take."""
    CONTINUE = "continue"           # Ask another question in current skill
    FOLLOW_UP = "follow_up"         # Drill deeper on the previous topic (candidate struggled)
    SWITCH_SKILL = "switch_skill"   # Move to the next skill module
    SKIP_SKILL = "skip_skill"       # Skip the next skill (candidate demonstrated mastery)
    ADJUST_DIFFICULTY = "adjust"    # Only adjust difficulty, keep same skill
    CONCLUDE = "conclude"           # End the interview early (candidate is clearly senior/junior)


@dataclass
class AgentDecision:
    """Structured output from the interview agent."""
    action: AgentAction
    reason: str = ""
    next_skill: str | None = None       # For SWITCH_SKILL / SKIP_SKILL
    new_difficulty: str | None = None    # For ADJUST_DIFFICULTY
    focus_topics: list[str] = field(default_factory=list)  # Topics to focus on
    follow_up_context: str | None = None  # What specifically to follow up on


AGENT_SYSTEM_PROMPT = """你是面试决策Agent。warmup固定1题不计分。根据表现决定: continue / follow_up(追问) / switch_skill(切模块) / skip_skill(跳过) / adjust(调难度) / conclude(结束)。

规则:
- warmup后直接switch_skill到technical_qa
- technical_qa占总量的百分之60左右，其余(behavioral/system_design/coding)分剩余题数
- 非技术板块(behavioral/system_design/coding)各最多3题，一般不追问
- 技术板块得分<50→follow_up(连追最多1次)
- 连续2题>85→skip或提难度，难度渐进调整
- 优先未问模块，剩余题不足时跳过未问的低优先级模块

输出JSON: {"action":"continue","reason":"...","next_skill":null,"new_difficulty":null,"focus_topics":[],"follow_up_context":null}"""


AGENT_OBSERVATION_TEMPLATE = """## 当前面试状态

### 候选人背景
- 技术栈：{tech_stack}
- 工作年限：{years_experience}
- 当前难度：{difficulty}

### 面试进度
- 当前技能模块：{current_skill}
- 已选技能模块（按顺序）：{skill_modules}
- 已提问总数：{total_asked} / {max_questions}
- 当前模块已提问数：{module_count}

### 最近回答历史（最多最近 5 题）
{recent_history}

### 各模块得分汇总
{module_scores}

请根据以上状态决定下一步动作，输出 JSON 决策。"""


class InterviewAgent:
    """LLM-driven agent that decides interview flow dynamically."""

    def __init__(self, llm_factory: LLMFactory, enabled: bool = True):
        self.llm_factory = llm_factory
        self.enabled = enabled
        self._consecutive_follow_ups: dict[str, int] = {}  # session_id -> count

    @staticmethod
    def _format_tech_stack(tech_stack: list) -> str:
        """Format tech_stack — top 5 only to keep prompt lean."""
        if not tech_stack:
            return "未知"
        names = []
        for item in tech_stack[:5]:
            if isinstance(item, dict):
                names.append(item.get("name", str(item)))
            else:
                names.append(str(item))
        return ", ".join(names)

    def _build_observation(
        self,
        tech_stack: list,
        years_experience: int | None,
        difficulty: str,
        current_skill: str,
        skill_modules: list[str],
        total_asked: int,
        max_questions: int,
        module_count: int,
        recent_history: list[dict],
        module_scores: dict[str, float],
        warmup_count: int = 0,
        warmup_max: int = 1,
        module_counts: dict | None = None,
    ) -> str:
        """Build the observation — scores + history first (most important), tech last."""

        counts = module_counts or {}

        # 1. Module progress: use module_counts to know which were visited
        progress_parts = []
        if warmup_count > 0:
            w_status = "V" if warmup_count >= warmup_max else f"{warmup_count}/{warmup_max}"
            progress_parts.append(f"warmup:{w_status}")
        for m in skill_modules:
            cnt = counts.get(m, 0)
            if cnt > 0:
                marker = f"V{cnt}"  # V2 = done, 2 questions asked
            else:
                marker = "O"
            progress_parts.append(f"{marker}{m}")
        progress_str = " ".join(progress_parts)

        # 2. Scores per module (most critical decision input)
        score_lines = []
        for mod, avg_score in sorted(module_scores.items(), key=lambda x: x[1], reverse=True):
            score_lines.append(f"{mod}={avg_score:.0f}")
        scores_str = " ".join(score_lines) if score_lines else "无"

        # 3. Recent Q&A — question + answer both abbreviated
        history_lines = []
        for i, h in enumerate(recent_history[-3:]):
            s = h.get('score')
            score_str = str(s) if s is not None else "?"
            q = h.get('question', '')
            q_short = (q[:80] + '...') if len(q) > 80 else q
            a = h.get('answer', '')
            a_short = (a[:100] + '...') if len(a) > 100 else a
            history_lines.append(f"[{i+1}]{h.get('skill','?')} Q:{q_short} A:{a_short} 得分{score_str}")
        history_str = " | ".join(history_lines) if history_lines else "无"

        # 4. Tech stack — top 5 only
        tech_str = self._format_tech_stack(tech_stack)

        observation = (
            f"进度:{progress_str} | 当前:{current_skill} | 难度:{difficulty} | {total_asked}/{max_questions}题\n"
            f"均分:{scores_str}\n"
            f"回答:{history_str}\n"
            f"技术栈:{tech_str} | 年限:{years_experience or '?'}\n"
            "决定动作,输出JSON。"
        )

        import logging
        _log = logging.getLogger(__name__)
        _log.warning("AGENT_OBSERVATION len=%d", len(observation))
        _log.warning("AGENT_OBSERVATION full:\n%s", observation)
        return observation

    async def decide(
        self,
        session_id: str,
        tech_stack: list,
        years_experience: int | None,
        difficulty: str,
        current_skill: str,
        skill_modules: list[str],
        total_asked: int,
        max_questions: int,
        module_count: int,
        recent_history: list[dict],
        module_scores: dict[str, float],
        warmup_count: int = 0,
        warmup_max: int = 1,
        module_counts: dict | None = None,
    ) -> AgentDecision:
        """Ask the LLM to decide the next interview action.

        Returns an AgentDecision with the chosen action.
        If agent is disabled or LLM fails, falls back to a deterministic
        rule-based decision.
        """
        if not self.enabled:
            return self._fallback_decision(
                difficulty, current_skill, skill_modules,
                total_asked, max_questions, module_count,
                recent_history,
            )

        observation = self._build_observation(
            tech_stack, years_experience, difficulty,
            current_skill, skill_modules, total_asked,
            max_questions, module_count, recent_history, module_scores,
            warmup_count=warmup_count, warmup_max=warmup_max,
            module_counts=module_counts,
        )

        try:
            llm = self.llm_factory.get_chat_model(
                temperature=0.3, streaming=False,
            )
            messages = [
                SystemMessage(content=AGENT_SYSTEM_PROMPT),
                HumanMessage(content=observation),
            ]
            response = await llm.ainvoke(messages)
            content = response.content.strip()

            # Strip markdown code fences if present
            if content.startswith("```"):
                content = content.split("\n", 1)[1]
                if content.endswith("```"):
                    content = content[:-3]

            data = json.loads(content)

            # Track consecutive follow-ups
            if data.get("action") == "follow_up":
                self._consecutive_follow_ups[session_id] = (
                    self._consecutive_follow_ups.get(session_id, 0) + 1
                )
                # Enforce max 1 consecutive follow-up
                if self._consecutive_follow_ups.get(session_id, 0) > 1:
                    data["action"] = "continue"
                    data["reason"] += " (已达最大追问次数，转为继续出题)"
                    self._consecutive_follow_ups[session_id] = 0
            else:
                self._consecutive_follow_ups[session_id] = 0

            decision = AgentDecision(
                action=AgentAction(data.get("action", "continue")),
                reason=data.get("reason", ""),
                next_skill=data.get("next_skill"),
                new_difficulty=data.get("new_difficulty"),
                focus_topics=data.get("focus_topics", []),
                follow_up_context=data.get("follow_up_context"),
            )

            logger.info(
                f"Agent decision for session {session_id}: "
                f"{decision.action} — {decision.reason}"
            )
            return decision

        except (json.JSONDecodeError, KeyError, Exception) as e:
            logger.warning(f"Agent decision failed, using fallback: {e}")
            return self._fallback_decision(
                difficulty, current_skill, skill_modules,
                total_asked, max_questions, module_count,
                recent_history,
            )

    def _fallback_decision(
        self,
        difficulty: str,
        current_skill: str,
        skill_modules: list[str],
        total_asked: int,
        max_questions: int,
        module_count: int,
        recent_history: list[dict],
    ) -> AgentDecision:
        """Deterministic fallback when LLM decision is unavailable."""
        # If last answer was weak, follow up
        if recent_history:
            last = recent_history[-1]
            last_score = last.get("score")
            if last_score is not None and last_score < 50:
                return AgentDecision(
                    action=AgentAction.FOLLOW_UP,
                    reason="上一题得分低于50，自动追问 (fallback)",
                    follow_up_context=last.get("question", ""),
                )

        # If module has enough questions, switch
        min_per_module = max_questions // len(skill_modules) if skill_modules else 3
        if module_count >= min_per_module:
            try:
                current_idx = skill_modules.index(current_skill)
                if current_idx + 1 < len(skill_modules):
                    return AgentDecision(
                        action=AgentAction.SWITCH_SKILL,
                        reason=f"当前模块已完成 {module_count} 题，切换到下一模块 (fallback)",
                        next_skill=skill_modules[current_idx + 1],
                    )
            except ValueError:
                pass

        # If max questions reached, conclude
        if total_asked >= max_questions:
            return AgentDecision(
                action=AgentAction.CONCLUDE,
                reason="已达到最大题数 (fallback)",
            )

        # Default: continue
        return AgentDecision(
            action=AgentAction.CONTINUE,
            reason="继续当前模块出题 (fallback)",
        )

    def reset_session(self, session_id: str) -> None:
        """Reset agent state for a session."""
        self._consecutive_follow_ups.pop(session_id, None)
