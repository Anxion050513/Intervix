"""Prompt template for extracting structured data from resumes."""
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import PydanticOutputParser
from pydantic import BaseModel, Field


class ResumeExtractionResult(BaseModel):
    """Structured resume extraction result."""
    name: str = Field(description="Candidate's full name")
    email: str | None = Field(default=None, description="Email address")
    phone: str | None = Field(default=None, description="Phone number")
    years_experience: int | None = Field(
        default=None, description="Total years of professional experience"
    )
    tech_stack: list[dict] = Field(
        default_factory=list,
        description="List of technologies with proficiency and years. "
        "Format: [{'name': 'Python', 'proficiency': 'advanced', 'years': 3}]",
    )
    work_history: list[dict] = Field(
        default_factory=list,
        description="Work experience. "
        "Format: [{'company': '...', 'role': '...', 'start_date': '...', 'end_date': '...', "
        "'achievements': ['...']}]",
    )
    education: list[dict] = Field(
        default_factory=list,
        description="Education history. "
        "Format: [{'school': '...', 'degree': '...', 'major': '...', 'year': 2020}]",
    )
    summary: str = Field(
        default="", description="A 2-3 sentence professional summary"
    )


# Create the parser
parser = PydanticOutputParser(pydantic_object=ResumeExtractionResult)

# Build the prompt template
RESUME_EXTRACTION_PROMPT = ChatPromptTemplate.from_messages([
    (
        "system",
        """你是一位专业的简历分析师。你的任务是从简历文本中提取结构化信息。

## 提取规则
1. **name**: 从简历开头提取姓名
2. **email**: 提取邮箱地址，找不到填 null
3. **phone**: 提取电话号码，找不到填 null
4. **years_experience**: 根据工作经历计算总年限，无法判断填 null
5. **tech_stack**: 列出所有技术技能，proficiency 根据简历描述判断：
   - beginner: 了解/熟悉
   - intermediate: 使用过/能独立开发
   - advanced: 精通/主导过项目/多年经验
   - expert: 深入研究/开源贡献/教学经验
   years 字段填该项技术的使用年数（根据工作经历推断）
6. **work_history**: 每段经历填 company, role, start_date, end_date, achievements(列表)
7. **education**: 每段教育填 school, degree, major, year
8. **summary**: 用 2-3 句话总结候选人

## 技术要求
- 所有日期统一为 "YYYY-MM" 格式，不确定具体月份填 "YYYY-01"
- tech_stack 要尽量详细，从项目描述中推断使用过的技术
- 不要编造信息，不确定的填 null

{format_instructions}"""
    ),
    (
        "user",
        "请分析以下简历文本，提取结构化信息：\n\n{resume_text}"
    ),
])

# Partially fill with format instructions
RESUME_EXTRACTION_PROMPT = RESUME_EXTRACTION_PROMPT.partial(
    format_instructions=parser.get_format_instructions()
)
