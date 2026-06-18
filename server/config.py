"""Application configuration via Pydantic Settings."""
import os
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # LLM (Chat)
    llm_api_key: str = "sk-xxx"
    llm_base_url: str = "https://api.openai.com/v1"
    llm_model: str = "gpt-4o"

    # Embedding (separate from LLM)
    embedding_api_key: str = "none"           # "none" = use local model
    embedding_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    embedding_model: str = "text-embedding-v4"

    # MySQL
    mysql_host: str = "localhost"
    mysql_port: int = 3306
    mysql_user: str = "root"
    mysql_password: str = "interview123"
    mysql_database: str = "ai_interviewer"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # JWT
    jwt_secret: str = "interview-jwt-secret-change-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 1440  # 24 hours

    # LangFuse Observability (optional — leave blank to disable)
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = "https://cloud.langfuse.com"

    # App
    app_env: str = "development"
    upload_dir: str = "./data/uploads"
    chroma_persist_dir: str = "./data/chroma"
    hf_endpoint: str = "https://hf-mirror.com"

    @property
    def database_url(self) -> str:
        return (
            f"mysql+aiomysql://{self.mysql_user}:{self.mysql_password}"
            f"@{self.mysql_host}:{self.mysql_port}/{self.mysql_database}"
            f"?charset=utf8mb4"
        )

    @property
    def is_development(self) -> bool:
        return self.app_env == "development"

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": False,
        "extra": "ignore",  # Ignore unknown env vars instead of crashing
    }


settings = Settings()
