"""FastAPI dependency injection."""
from server.config import settings
from server.ai.llm import LLMFactory


def get_llm_factory() -> LLMFactory:
    """Return a configured LLM factory instance."""
    return LLMFactory(
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
        model=settings.llm_model,
    )
