"""Coding Challenge Skill — hands-on programming questions with MCP sandbox execution."""
import logging

from server.ai.skills.base import BaseSkill, SkillContext, GeneratedQuestion
from server.ai.llm import LLMFactory

logger = logging.getLogger(__name__)


class CodingChallengeSkill(BaseSkill):
    name = "coding_challenge"
    display_name = "编程挑战"
    priority = 50  # Run last before scoring
    min_questions = 1
    max_questions = 3

    def __init__(self, llm_factory: LLMFactory):
        self.llm_factory = llm_factory

    async def generate_question(self, ctx: SkillContext) -> GeneratedQuestion:
        llm = self.llm_factory.get_chat_model(temperature=0.4, max_tokens=3000)
        prompt = f"""你是一个编程面试官。根据候选人背景出一道编程题。

候选人技术栈：{', '.join([t.get('name', '') for t in ctx.tech_stack[:5]])}
工作经验：{ctx.years_experience or '未知'} 年
难度：{ctx.difficulty}

要求：
1. 题目应该是中等难度算法题或实际编程场景
2. 提供函数签名/模板
3. 给出 2-3 个测试用例
4. 题目描述用纯文字，禁止 Markdown 语法（**粗体**、- 列表等），代码部分用注释说明

输出 JSON：
{{"question": "题目描述（中文，纯文字）", "template": "def solution(...):", "test_cases": [{{"input": "...", "expected": "..."}}], "difficulty": "medium"}}

只输出 JSON。"""

        result = await llm.ainvoke(prompt)
        import json
        try:
            data = json.loads(result.content.strip())
        except json.JSONDecodeError:
            data = {
                "question": "请实现一个函数，反转字符串中的单词顺序。",
                "template": "def reverse_words(s: str) -> str:",
                "test_cases": [{"input": "hello world", "expected": "world hello"}],
                "difficulty": "medium",
            }

        return GeneratedQuestion(
            text=data["question"],
            question_type="coding",
            expected_topics=["coding", "algorithm"],
            reference_answer=data.get("template", ""),
            metadata={
                "template": data.get("template", ""),
                "test_cases": data.get("test_cases", []),
                "difficulty": data.get("difficulty", ctx.difficulty),
            },
        )

    async def evaluate_answer(
        self,
        question: GeneratedQuestion,
        user_answer: str,
        ctx: SkillContext,
    ) -> dict:
        llm = self.llm_factory.get_chat_model(temperature=0.2, max_tokens=500)

        # Try sandbox execution if MCP available
        sandbox_info = ""
        try:
            from server.mcp.sandbox import execute_code_sandboxed
            sandbox_result = await execute_code_sandboxed(user_answer, question.metadata.get("test_cases", []))
            sandbox_info = (
                f"沙箱执行结果：\n"
                f"passed: {sandbox_result.get('passed', 0)}/{sandbox_result.get('total', 0)}\n"
                f"stdout: {sandbox_result.get('stdout', '')[:500]}\n"
                f"stderr: {sandbox_result.get('stderr', '')[:500]}\n"
                f"exit_code: {sandbox_result.get('exit_code', '')}\n"
            )
        except Exception:
            sandbox_info = "(沙箱不可用，基于代码文本评估)\n"

        prompt = f"""评估候选人的编程题回答。

题目：{question.text}
模板：{question.metadata.get('template', '')}

候选人代码：
```
{user_answer[:2000]}
```

{sandbox_info}
评分维度（总分100，必须包含以下4个标准维度）：
- technical_accuracy 技术准确度 (40%): 代码逻辑是否正确、正确性
- depth_breadth 深度与广度 (25%): 时间/空间复杂度、算法选型
- clarity 表达清晰度 (20%): 命名规范、结构清晰、可读性
- practical_experience 实践经验 (15%): 边界条件、异常处理、工程化意识

输出 JSON（score_breakdown 必须包含以上4个维度）：
{{"score": 85, "score_breakdown": {{"technical_accuracy": 90, "depth_breadth": 80, "clarity": 85, "practical_experience": 80}}, "feedback": "具体改进建议（中文）"}}

只输出 JSON。"""

        result = await llm.ainvoke(prompt)
        import json
        try:
            return json.loads(result.content.strip())
        except json.JSONDecodeError:
            return {"score": 70, "score_breakdown": {"technical_accuracy": 70, "depth_breadth": 70, "clarity": 70, "practical_experience": 70}, "feedback": "评分解析失败"}

    def _extract_code(self, text: str) -> str | None:
        """Extract code from markdown-style code blocks."""
        if "```" in text:
            # Find first code block
            start = text.find("```")
            start = text.find("\n", start) + 1
            end = text.find("```", start)
            if end != -1:
                return text[start:end].strip()
        return text.strip() if text.strip() else None
