"""Skill registry — discovers and manages skill modules."""
from typing import Type

from server.ai.skills.base import BaseSkill


class SkillRegistry:
    """Registry for interview skill modules.

    Skills are registered by name and ordered by priority.
    """

    def __init__(self):
        self._skills: dict[str, BaseSkill] = {}

    def register(self, skill: BaseSkill) -> None:
        """Register a skill instance."""
        self._skills[skill.name] = skill

    def get(self, name: str) -> BaseSkill | None:
        """Get a skill by name."""
        return self._skills.get(name)

    def get_all(self) -> list[BaseSkill]:
        """Get all registered skills, sorted by priority."""
        return sorted(self._skills.values(), key=lambda s: s.priority)

    def get_by_names(self, names: list[str]) -> list[BaseSkill]:
        """Get skills by names, sorted by priority."""
        skills = [self._skills[n] for n in names if n in self._skills]
        return sorted(skills, key=lambda s: s.priority)

    def get_by_type(self, question_type: str) -> list[BaseSkill]:
        """Get skills that handle a given question type."""
        return [
            s for s in self._skills.values()
            if hasattr(s, 'question_type') and s.question_type == question_type
        ]

    @property
    def skill_count(self) -> int:
        return len(self._skills)


# Global singleton
skill_registry = SkillRegistry()
