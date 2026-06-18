"""Initialize and register all skill modules."""
from server.ai.llm import LLMFactory
from server.ai.skills.registry import skill_registry
from server.ai.skills.warmup import WarmupSkill
from server.ai.skills.technical_qa import TechnicalQASkill
from server.ai.skills.behavioral import BehavioralSkill
from server.ai.skills.system_design import SystemDesignSkill
from server.ai.skills.coding_challenge import CodingChallengeSkill


def register_all_skills(llm_factory: LLMFactory):
    """Register all available skill modules in the skill registry."""
    skill_registry.register(WarmupSkill(llm_factory))
    skill_registry.register(TechnicalQASkill(llm_factory))
    skill_registry.register(BehavioralSkill(llm_factory))
    skill_registry.register(SystemDesignSkill(llm_factory))
    skill_registry.register(CodingChallengeSkill(llm_factory))
