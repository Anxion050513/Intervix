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

        llm = self.llm_factory.get_chat_model(temperature=0.7)
        techs = [
            t.get("name", "") for t in ctx.tech_stack
            if t.get("name", "") not in self._used_topics
        ]
        if not techs:
            techs = [t.get("name", "") for t in ctx.tech_stack[:5]]

        tech_list = ", ".join(techs[:8])
        difficulty = ctx.difficulty
        history = self._format_history(ctx.session_history[-6:])

        prompt = f"""你是一位资深技术面试官，正在进行技术问答环节。

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
4. 直接输出问题，用中文提问

输出格式：
问题：[问题内容]
参考要点：[3-5个候选答案应该覆盖的核心要点]"""

        result = await llm.ainvoke(prompt)
        content = result.content.strip()

        # Parse question and reference
        question_text = content
        reference = ""
        if "问题：" in content and "参考要点：" in content:
            parts = content.split("参考要点：", 1)
            question_text = parts[0].replace("问题：", "").strip()
            reference = parts[1].strip()

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
        llm = self.llm_factory.get_chat_model(temperature=0.2)

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
        if not history:
            return "（无）"
        lines = []
        for i, qa in enumerate(history, 1):
            lines.append(
                f"{i}. Q: {qa.get('question', '')[:80]}...\n"
                f"   A: {qa.get('answer', '')[:80]}..."
            )
        return "\n".join(lines)

    async def on_session_start(self, ctx: SkillContext) -> None:
        self._asked_count = 0
        self._used_topics = set()
