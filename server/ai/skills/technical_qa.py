"""Technical Q&A interview skill with RAG support."""
from server.ai.skills.base import BaseSkill, SkillContext, GeneratedQuestion
from server.ai.llm import LLMFactory


class TechnicalQASkill(BaseSkill):
    name = "technical_qa"
    display_name = "技术问答"
    priority = 2
    min_questions = 3
    max_questions = 6

    def __init__(self, llm_factory: LLMFactory):
        self.llm_factory = llm_factory
        self._asked_count = 0
        self._used_topics: set[str] = set()

    async def generate_question(self, ctx: SkillContext) -> GeneratedQuestion:
        self._asked_count += 1

        import logging as _logging
        _log = _logging.getLogger(__name__)

        llm = self.llm_factory.get_chat_model(temperature=0.7, max_tokens=4000)
        techs = [
            t.get("name", "") for t in ctx.tech_stack
            if t.get("name", "") not in self._used_topics
        ]
        if not techs:
            techs = [t.get("name", "") for t in ctx.tech_stack[:5]]

        tech_list = ", ".join(techs[:8])
        difficulty = ctx.difficulty
        history = self._format_history(ctx.session_history[-6:])

        # --- Step 1: Generate question only ---
        q_prompt = f"""你是一位资深技术面试官，正在进行技术问答环节。

候选人技术栈：{tech_list}
工作经验：{ctx.years_experience or '未知'} 年
当前难度：{difficulty}
已回答问题：
{history}

请生成第 {self._asked_count} 个技术面试问题。

难度要求：
- easy: 基础概念和用法
- medium: 原理理解和实践经验
- hard: 深入原理、优化、对比、架构设计

要求：
1. 问题基于候选人的技术栈（优先问尚未问过的技术）
2. 问题要有深度，不能是简单的"什么是XXX"
3. 如果是 medium/hard，应该让候选人需要结合实际经验回答
4. 只输出问题本身，用中文，控制在150字以内"""

        q_result = await llm.ainvoke(q_prompt)
        question_text = q_result.content.strip()
        q_finish = q_result.response_metadata.get("finish_reason", "unknown")
        q_tokens = q_result.response_metadata.get("token_usage", {})
        _log.warning(
            "TECHNICAL_QA_QUESTION finish=%s completion_tk=%s len=%d content=%s",
            q_finish, q_tokens.get("completion_tokens", "?"),
            len(question_text), question_text[:150].replace('\n', '\\n')
        )

        # --- Step 2: Generate reference points based on the question ---
        r_llm = self.llm_factory.get_chat_model(temperature=0.3, max_tokens=2000)
        r_prompt = f"""你是一位资深技术面试官。请为以下面试问题，列出3-5个候选答案应该覆盖的核心要点。

面试问题：{question_text}
候选人技术栈：{tech_list}
难度：{difficulty}

要求：
1. 每条要点控制在30字以内
2. 每条单独一行，用序号列出
3. 只输出要点，不要任何额外说明"""

        r_result = await r_llm.ainvoke(r_prompt)
        reference = r_result.content.strip()
        r_finish = r_result.response_metadata.get("finish_reason", "unknown")
        r_tokens = r_result.response_metadata.get("token_usage", {})
        _log.warning(
            "TECHNICAL_QA_REFERENCE finish=%s completion_tk=%s len=%d content=%s",
            r_finish, r_tokens.get("completion_tokens", "?"),
            len(reference), reference[:200].replace('\n', '\\n')
        )

        # Track used tech
        for tech in techs:
            if tech.lower() in question_text.lower():
                self._used_topics.add(tech)
                break

        return GeneratedQuestion(
            text=question_text,
            question_type="technical",
            expected_topics=techs[:5],
            reference_answer=reference,
            metadata={
                "skill": "technical_qa",
                "index": self._asked_count,
                "difficulty": difficulty,
            },
        )

    async def evaluate_answer(
        self, question: GeneratedQuestion, user_answer: str, ctx: SkillContext
    ) -> dict:
        llm = self.llm_factory.get_chat_model(temperature=0.2, max_tokens=500)

        prompt = f"""你是一位资深技术面试官，请评估候选人对以下技术问题的回答。

## 面试问题
{question.text}

## 参考要点
{question.reference_answer or '无'}

## 候选人的回答
{user_answer}

## 评分维度（总分100）
- 技术准确度 (40%): 回答的技术内容是否正确、准确
- 深度与广度 (25%): 是否深入原理，是否有扩展思考
- 表达清晰度 (20%): 逻辑是否清晰，表达是否流畅
- 实践经验 (15%): 是否能结合实际项目经验

## 输出格式（JSON）
{{
  "score": 85,
  "score_breakdown": {{
    "technical_accuracy": 90,
    "depth_breadth": 80,
    "clarity": 85,
    "practical_experience": 85
  }},
  "feedback": "具体、可操作的改进建议（中文）"
}}

只输出 JSON，不要加其他内容。"""

        result = await llm.ainvoke(prompt)
        import json
        try:
            return json.loads(result.content.strip())
        except json.JSONDecodeError:
            return {
                "score": 70,
                "score_breakdown": {
                    "technical_accuracy": 70,
                    "depth_breadth": 70,
                    "clarity": 70,
                    "practical_experience": 70,
                },
                "feedback": "评分解析失败，请手动评估。原始内容：" + result.content[:200],
            }

    def _format_history(self, history: list) -> str:
        import logging
        _log = logging.getLogger(__name__)
        _log.warning("FORMAT_HISTORY_DEBUG items=%d keys_per_item=%s",
                     len(history),
                     [list(h.keys()) if isinstance(h, dict) else type(h).__name__ for h in history])
        if not history:
            return "（无）"
        lines = []
        for i, item in enumerate(history, 1):
            if item.get("type") == "follow_up_hint":
                lines.append(
                    f"{i}. [追问要求] {item.get('context', '')}"
                )
            else:
                q = item.get('question', '')
                a = item.get('answer', '')
                _log.warning("FORMAT_HISTORY_DEBUG item=%d q_len=%d a_len=%d a_preview=%s",
                             i, len(q), len(a), a[:80])
                if not a:
                    a = "(答案未记录，可能被安全护栏拦截)"
                    _log.warning("FORMAT_HISTORY_DEBUG item %d has empty answer, question[:60]=%s", i, q[:60])
                lines.append(
                    f"{i}. Q: {q[:1000]}{'...' if len(q) > 1000 else ''}\n"
                    f"   A: {a[:2500]}{'...' if len(a) > 2500 else ''}"
                )
        return "\n".join(lines)

    async def on_session_start(self, ctx: SkillContext) -> None:
        self._asked_count = 0
        self._used_topics = set()
