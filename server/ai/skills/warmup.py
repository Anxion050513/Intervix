"""Warmup / icebreaker interview skill."""
import json

from server.ai.skills.base import BaseSkill, SkillContext, GeneratedQuestion
from server.ai.llm import LLMFactory
from server.config import settings


class WarmupSkill(BaseSkill):
    name = "warmup"
    display_name = "热身面试"
    priority = 1
    min_questions = 1
    max_questions = 2

    def __init__(self, llm_factory: LLMFactory):
        self.llm_factory = llm_factory
        self._asked_count = 0

    async def generate_question(self, ctx: SkillContext) -> GeneratedQuestion:
        self._asked_count += 1

        llm = self.llm_factory.get_chat_model(temperature=0.8)
        techs = ", ".join([t.get("name", "") for t in ctx.tech_stack[:5]])
        years = ctx.years_experience or "未知"

        prompt = f"""你是一位友好的面试官，这是面试的开场热身环节。

候选人信息：
- 技术栈：{techs}
- 工作经验：{years} 年
- 简历摘要：{ctx.resume_data.get('summary', '')}

这是第 {self._asked_count} 个热身问题。如果是第1个，请候选人做简短自我介绍。
如果是第2个，问一个关于职业规划或项目经历的开放式问题。

请用友好、鼓励的语气。直接输出问题，不要加前缀。"""

        result = await llm.ainvoke(prompt)
        question_text = result.content.strip()

        return GeneratedQuestion(
            text=question_text,
            question_type="warmup",
            expected_topics=["自我介绍", "职业规划"],
            metadata={"skill": "warmup", "index": self._asked_count},
        )

    async def evaluate_answer(
        self, question: GeneratedQuestion, user_answer: str, ctx: SkillContext
    ) -> dict:
        # Warmup: light scoring with standard dimensions for report aggregation
        llm = self.llm_factory.get_chat_model(temperature=0.2)
        prompt = f"""快速评估热身环节的回答（仅用于维度分析，不显示分数）。

问题：{question.text}
回答：{user_answer}

从以下4个维度打分（0-100）：
- technical_accuracy: 对自身技术背景的描述准确度
- depth_breadth: 经历的丰富程度
- clarity: 表达清晰度
- practical_experience: 实际项目经验体现

输出 JSON：{{"score_breakdown": {{"technical_accuracy": 80, "depth_breadth": 75, "clarity": 85, "practical_experience": 80}}}}
只输出 JSON。"""

        try:
            result = await llm.ainvoke(prompt)
            data = json.loads(result.content.strip())
            return {
                "score": None,  # Warmup is not scored
                "score_breakdown": data.get("score_breakdown", {
                    "technical_accuracy": 70, "depth_breadth": 70,
                    "clarity": 70, "practical_experience": 70,
                }),
                "feedback": "热身环节，感谢你的回答！",
            }
        except (json.JSONDecodeError, Exception):
            return {
                "score": None,
                "score_breakdown": {
                    "technical_accuracy": 70, "depth_breadth": 70,
                    "clarity": 70, "practical_experience": 70,
                },
                "feedback": "热身环节，感谢你的回答！",
            }

    async def on_session_start(self, ctx: SkillContext) -> None:
        self._asked_count = 0
