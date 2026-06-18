"""Base skill abstract class and context."""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class SkillContext:
    """Context passed to each skill for question generation and evaluation."""
    resume_data: dict = field(default_factory=dict)
    tech_stack: list = field(default_factory=list)
    years_experience: int | None = None
    session_history: list = field(default_factory=list)
    difficulty: str = "medium"
    session_id: str = ""
    question_count: int = 10


@dataclass
class GeneratedQuestion:
    """Result of skill.generate_question()."""
    text: str
    question_type: str  # warmup / technical / behavioral / system_design / coding
    expected_topics: list = field(default_factory=list)
    reference_answer: str | None = None
    metadata: dict = field(default_factory=dict)


class BaseSkill(ABC):
    """Abstract base for all interview skill modules."""

    name: str = "base"
    display_name: str = "Base Skill"
    priority: int = 0  # Lower numbers run earlier
    min_questions: int = 3
    max_questions: int = 7

    @abstractmethod
    async def generate_question(self, ctx: SkillContext) -> GeneratedQuestion:
        """Generate the next interview question given context."""
        ...

    @abstractmethod
    async def evaluate_answer(
        self,
        question: GeneratedQuestion,
        user_answer: str,
        ctx: SkillContext,
    ) -> dict:
        """Score and provide feedback for an answer.

        Returns:
            dict with keys: score (float 0-100), score_breakdown (dict),
            feedback (str)
        """
        ...

    async def on_session_start(self, ctx: SkillContext) -> None:
        """Called when an interview session begins."""
        pass

    async def on_session_end(self, ctx: SkillContext) -> None:
        """Called when an interview session ends."""
        pass
