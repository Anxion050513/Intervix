"""System design interview skill."""
from server.ai.skills.base import BaseSkill, SkillContext, GeneratedQuestion
from server.ai.llm import LLMFactory


class SystemDesignSkill(BaseSkill):
    name = "system_design"
    display_name = "系统设计"
    priority = 4
    min_questions = 1
    max_questions = 3

    SCENARIOS = {
        "easy": [
            "设计一个短链接服务（URL Shortener）",
            "设计一个简单的REST API限流系统",
        ],
        "medium": [
            "设计一个类似Twitter的信息流系统",
            "设计一个分布式消息队列",
            "设计一个秒杀系统",
        ],
        "hard": [
            "设计一个支持亿级用户的实时聊天系统",
            "设计一个全球CDN网络",
            "设计一个电商推荐系统",
        ],
    }

    def __init__(self, llm_factory: LLMFactory):
        self.llm_factory = llm_factory

    async def generate_question(self, ctx: SkillContext) -> GeneratedQuestion:
        scenarios = self.SCENARIOS.get(ctx.difficulty, self.SCENARIOS["medium"])
        import random
        scenario = random.choice(scenarios)

        llm = self.llm_factory.get_chat_model(temperature=0.7, max_tokens=3000)

        prompt = f"""你是一位系统设计面试官。

候选人经验：{ctx.years_experience or '未知'} 年
设计题目：{scenario}

请完善这个系统设计面试题。输出：
1. 清晰的场景描述
2. 功能需求和非功能需求
3. 初步提示（可选，帮助候选人入题）

用中文，专业但引导性强的语气。直接在对话中呈现给候选人。"""

        result = await llm.ainvoke(prompt)

        return GeneratedQuestion(
            text=result.content.strip(),
            question_type="system_design",
            expected_topics=["scalability", "availability", "data modeling", "trade-offs"],
            metadata={"scenario": scenario},
        )

    async def evaluate_answer(
        self, question: GeneratedQuestion, user_answer: str, ctx: SkillContext
    ) -> dict:
        llm = self.llm_factory.get_chat_model(temperature=0.2, max_tokens=500)

        prompt = f"""评估候选人的系统设计回答。

设计题目：{question.metadata.get('scenario', '')}
回答：{user_answer}

评分维度（总分100，必须包含以下4个标准维度 + 可选领域维度）：
- technical_accuracy 技术准确度 (30%): 需求分析、架构方案是否合理
- depth_breadth 深度与广度 (30%): 是否考虑扩展性、并发、容量
- clarity 表达清晰度 (20%): 逻辑是否清晰、表达是否流畅
- practical_experience 实践经验 (20%): 是否能结合项目经验分析 trade-offs

输出 JSON（score_breakdown 必须包含以上4个维度）：
{{"score": 80, "score_breakdown": {{"technical_accuracy": 85, "depth_breadth": 80, "clarity": 80, "practical_experience": 75}}, "feedback": "具体改进建议（中文）"}}

只输出 JSON。"""

        result = await llm.ainvoke(prompt)
        import json
        try:
            return json.loads(result.content.strip())
        except json.JSONDecodeError:
            return {"score": 70, "score_breakdown": {"technical_accuracy": 70, "depth_breadth": 70, "clarity": 70, "practical_experience": 70}, "feedback": "评分解析失败"}

    async def on_session_start(self, ctx: SkillContext) -> None:
        pass
