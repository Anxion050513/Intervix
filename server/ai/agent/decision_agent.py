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


AGENT_SYSTEM_PROMPT = """你是一个资深技术面试官 Agent，负责动态决策面试流程。

## 你的职责
观察候选人当前面试状态（已回答的问题、得分、当前技能模块），决定下一步最优动作。

## 可选动作
- **continue**: 当前技能模块下继续出下一道题（候选人表现正常）
- **follow_up**: 追问上一道题的相关知识点（候选人回答有漏洞、不完整或得分 < 60）
- **switch_skill**: 切换到下一个技能模块（当前模块问题数已达上限，或候选人表现优异无需更多题）
- **skip_skill**: 跳过某个技能模块（候选人简历/回答中已展示该领域深度掌握）
- **adjust**: 仅调整难度，保持当前技能模块
- **conclude**: 提前结束面试（候选人明显超出或低于岗位要求，无需继续所有轮次）

## 决策原则
1. 如果上一题得分 < 50，应该 follow_up 深入追问，确认是知识盲区还是紧张
2. 如果连续 3 题得分 > 85，可以 skip_skill 或提升难度
3. 同一技能模块内，follow_up 最多连续 1 次，之后必须 continue 或 switch_skill
4. 难度调整要渐进：medium→hard 或 medium→easy，不要跨级跳
5. 剩余可用题数不足时，优先 cover 尚未提问的技能模块
6. 如果候选人工作经验 > 8 年，warmup 只需要 1 题即可 switch_skill

## 输出格式
严格输出 JSON，不要带 markdown 标记：

{
  "action": "continue",
  "reason": "候选人上一题回答正确率 75%，属于正常水平，继续当前模块出题",
  "next_skill": null,
  "new_difficulty": null,
  "focus_topics": [],
  "follow_up_context": null
}
"""


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
        """Format tech_stack (list of dicts or strings) into a readable string."""
        if not tech_stack:
            return "未知"
        result_parts = []
        for item in tech_stack:
            if isinstance(item, dict):
                name = item.get("name", str(item))
                proficiency = item.get("proficiency", "")
                years = item.get("years", "")
                if proficiency or years:
                    result_parts.append(f"{name}({proficiency}/{years}年)")
                else:
                    result_parts.append(name)
            else:
                result_parts.append(str(item))
        return ", ".join(result_parts)

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
    ) -> str:
        """Build the observation text for the agent."""

        # Format recent history
        history_lines = []
        for i, h in enumerate(recent_history[-5:]):
            score_str = str(h.get('score', 'N/A')) if h.get('score') is not None else "未评分"
            q = h.get('question', '')
            history_lines.append(
                f"  [{i+1}] 模块: {h.get('skill', 'N/A')} | "
                f"问题: {q[:3000]}{'...' if len(q) > 3000 else ''} | "
                f"得分: {score_str}"
            )
        history_text = "\n".join(history_lines) if history_lines else "  (尚无回答记录)"

        # Format module scores
        score_lines = []
        for mod, avg_score in module_scores.items():
            score_lines.append(f"  {mod}: 平均 {avg_score:.1f} 分")
        scores_text = "\n".join(score_lines) if score_lines else "  (尚无评分数据)"

        # Build observation, escaping { } in user-generated text to prevent
        # str.format() from crashing on code snippets / JSON in answers.
        safe = lambda s: s.replace('{', '{{').replace('}', '}}') if isinstance(s, str) else s
        observation = AGENT_OBSERVATION_TEMPLATE.format(
            tech_stack=safe(self._format_tech_stack(tech_stack)),
            years_experience=safe(years_experience or "未知"),
            difficulty=safe(difficulty),
            current_skill=safe(current_skill),
            skill_modules=safe(" → ".join(skill_modules)),
            total_asked=total_asked,
            max_questions=max_questions,
            module_count=module_count,
            recent_history=safe(history_text),
            module_scores=safe(scores_text),
        )
        import logging
        _log = logging.getLogger(__name__)
        _log.warning(
            "AGENT_OBSERVATION len=%d\n---OBSERVATION---\n%s\n---END---",
            len(observation), observation
        )
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
