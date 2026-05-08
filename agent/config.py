"""
Централизованная конфигурация через pydantic-settings.
Заменяет разрозненные os.getenv() вызовы.
"""
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings
from typing import Optional, Literal
import os

class Settings(BaseSettings):
    # === LLM / vLLM ===
    vllm_base: str = Field(default="http://vllm:8000/v1", env="OPENAI_API_BASE")
    vllm_model: str = Field(default="Qwen/Qwen2.5-14B-Instruct-AWQ", env="VLLM_MODEL")
    vllm_api_key: str = Field(default="empty", env="OPENAI_API_KEY")
    
    # === Базы данных ===
    postgres_dsn: str = Field(..., env="DATABASE_URL")  # Обязательно!
    neo4j_uri: str = Field(default="bolt://neo4j:7687", env="NEO4J_URI")
    neo4j_user: str = Field(default="neo4j", env="NEO4J_USER")
    neo4j_password: str = Field(..., env="NEO4J_PASSWORD")  # Обязательно!
    
    qdrant_url: str = Field(default="http://qdrant:6333", env="QDRANT_URL")
    qdrant_collection: str = Field(default="devops_knowledge", env="QDRANT_COLLECTION")
    
    # === GitLab ===
    gitlab_url: str = Field(default="https://gitlab.dash-panel.tech", env="GITLAB_URL")
    gitlab_token: str = Field(..., env="GITLAB_TOKEN")  # Обязательно!
    gitlab_default_project: str = Field(default="dash-panel/backend", env="GITLAB_DEFAULT_PROJECT")
    
    # === Агент ===
    agent_mode: Literal["autonomous", "advisory"] = Field(default="advisory", env="AGENT_MODE")
    confidence_threshold: float = Field(default=0.7, ge=0.0, le=1.0, env="CONFIDENCE_THRESHOLD")
    max_retry: int = Field(default=3, ge=1, le=10, env="MAX_RETRY")
    
    # === Безопасность ===
    enable_guardrails: bool = Field(default=True, env="ENABLE_GUARDRAILS")
    audit_log_path: str = Field(default="./logs/audit.jsonl", env="AUDIT_LOG_PATH")
    
    # === Пути ===
    models_dir: str = Field(default="/data/models", env="MODELS_DIR")
    lora_dir: str = Field(default="./lora_adapters", env="LORA_DIR")
    
    @field_validator('gitlab_token', 'neo4j_password', 'postgres_dsn')
    @classmethod
    def validate_not_empty(cls, v: str, info) -> str:
        if not v or v.strip() == "":
            raise ValueError(f"{info.field_name} cannot be empty. Please set it in .env")
        return v.strip()
    
    @field_validator('confidence_threshold')
    @classmethod
    def validate_confidence(cls, v: float) -> float:
        if v < 0.5:
            import warnings
            warnings.warn("confidence_threshold < 0.5 may cause unsafe auto-execution")
        return v
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True

# Глобальный экземпляр для импорта
settings = Settings()

# Экспорт для удобства
__all__ = ['settings', 'Settings']
