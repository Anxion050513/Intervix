"""Behavioral interview skill (STAR method)."""
from server.ai.skills.base import BaseSkill, SkillContext, GeneratedQuestion
from server.ai.llm import LLMFactory


class BehavioralSkill(BaseSkill):
    name = "behavioral"
    display_name = "行为面试"
    priority = 3
    min_questions = 1
    max_questions = 3

    BEHAVIORAL_TOPICS = [
        "团队协作与冲突处理",
        "项目推进与交付",
        "技术难点攻克",
        "学习与成长",
        "领导力与影响力",
    ]

    def __init__(self, llm_factory: LLMFactory):
        self.llm_factory = llm_factory
        self._asked_count = 0
        self._used_topics: set = set()

    async def generate_question(self, ctx: SkillContext) -> GeneratedQuestion:
        self._asked_count += 1

        available = [t for t in self.BEHAVIORAL_TOPICS if t not in self._used_topics]
        if not available:
            available = self.BEHAVIORAL_TOPICS

        topic = available[self._asked_count % len(available)]
        self._used_topics.add(topic)

        llm = self.llm_factory.get_chat_model(temperature=0.8, max_tokens=3000)

        prompt = f"""你是一位资深 HR 面试官，正在进行行为面试。

候选人背景：{ctx.years_experience or '未知'} 年经验
技术栈：{', '.join([t.get('name', '') for t in ctx.tech_stack[:5]])}
当前主题：{topic}

请用 STAR 法则（Situation-Task-Action-Result）设计一个行为面试问题。
问题应该引导候选人描述具体的情景、任务、行动和结果。

要求：
1. 直接输出问题，不要加"好的""哇"等感叹词或寒暄前缀
2. 问题控制在200字以内，简洁有力
3. 用中文提问，语气专业但友好
4. 禁止使用任何 Markdown 语法（**粗体**、## 标题等），纯文字输出"""

        result = await llm.ainvoke(prompt)
        text = result.content.strip()
        # Detect and log truncation
        if text and not text.endswith(('？', '？', '。', '！', '!', '.', '?')):
            import logging
            logging.getLogger(__name__).warning(
                "BEHAVIORAL_QUESTION may be truncated (len=%d, ends_with=%r): %s",
                len(text), text[-20:], text[:100]
            )
        return GeneratedQuestion(
            text=text,
            question_type="behavioral",
            expected_topics=[topic],
            metadata={"skill": "behavioral", "index": self._asked_count},
        )

    async def evaluate_answer(
        self, question: GeneratedQuestion, user_answer: str, ctx: SkillContext
    ) -> dict:
        llm = self.llm_factory.get_chat_model(temperature=0.2, max_tokens=500)

        prompt = f"""评估候选人的行为面试回答（STAR 法则）。

问题：{question.text}
主题：{question.expected_topics}
回答：{user_answer}

评分维度（总分100，必须包含以下4个标准维度）：
- technical_accuracy 技术准确度 (30%): 回答中涉及的技术判断是否准确
- depth_breadth 深度与广度 (30%): STAR 完整性、具体细节和数据
- clarity 表达清晰度 (20%): 结构化表达、逻辑流畅度
- practical_experience 实践经验 (20%): 经验总结、反思深度、可迁移性

输出 JSON（score_breakdown 必须包含以上4个维度）：
{{"score": 85, "score_breakdown": {{"technical_accuracy": 80, "depth_breadth": 85, "clarity": 85, "practical_experience": 90}}, "feedback": "具体改进建议（中文）"}}

只输出 JSON。"""

        result = await llm.ainvoke(prompt)
        import json
        try:
            return json.loads(result.content.strip())
        except json.JSONDecodeError:
            return {"score": 70, "score_breakdown": {"technical_accuracy": 70, "depth_breadth": 70, "clarity": 70, "practical_experience": 70}, "feedback": "评分解析失败"}

    async def on_session_start(self, ctx: SkillContext) -> None:
        self._asked_count = 0
        self._used_topics = set()
