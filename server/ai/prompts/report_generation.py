"""Prompt template for generating the final interview report."""
from langchain_core.prompts import ChatPromptTemplate

REPORT_GENERATION_PROMPT = ChatPromptTemplate.from_messages([
    (
        "system",
        """你是一位面试评估专家。请根据候选人在面试中的表现，生成一份全面的评估报告。

## 报告要求
1. 总体评价：用一段话概括候选人的整体表现
2. 维度分析：从以下维度评估（每个维度 0-100）
   - 技术能力 (technical_ability)
   - 问题解决 (problem_solving)
   - 沟通表达 (communication)
   - 系统思维 (system_thinking)
3. 技能模块分析：按面试环节分析表现
4. 改进建议：3-5条具体、可操作的建议，按优先级排列

{format_instructions}"""
    ),
    (
        "user",
        """## 候选人背景
技术栈：{tech_stack}
工作经验：{years_experience} 年

## 面试记录
{interview_records}

## 各题得分
{question_scores}

请生成评估报告。"""
    ),
])
