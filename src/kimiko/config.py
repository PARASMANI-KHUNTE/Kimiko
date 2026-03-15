"""Kimiko configuration — Pydantic settings with environment-aware loading."""

from __future__ import annotations

from enum import Enum
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(str, Enum):
    DEVELOPMENT = "development"
    PRODUCTION = "production"


class Settings(BaseSettings):
    """Core settings loaded from environment variables prefixed with KIMIKO_."""

    model_config = SettingsConfigDict(
        env_prefix="KIMIKO_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Environment ──
    env: Environment = Environment.DEVELOPMENT

    # ── API ──
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_secret_key: str = "change-me-in-production"
    api_debug: bool = False
    debug_prompt: bool = False

    # ── Ollama ──
    ollama_base_url: str = "http://localhost:11434"
    default_model: str = "qwen2.5"
    embedding_model: str = "nomic-embed-text"

    # ── Redis ──
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/1"

    # ── PostgreSQL ──
    database_url: str = "postgresql+asyncpg://kimiko:kimiko@localhost:5432/kimiko"

    # ── Qdrant ──
    qdrant_url: str = "http://localhost:6333"
    qdrant_collection: str = "memories"
    vector_size: int = 768

    # ── Memory ──
    session_ttl_seconds: int = 3600          # 1 hour
    summary_ttl_seconds: int = 86400         # 24 hours
    conversation_summary_threshold: int = 20

    # ── Rate Limiting ──
    rate_limit_rpm: int = 60
    rate_limit_agent_steps_per_hour: int = 200
    rate_limit_max_tokens_per_request: int = 16384

    # ── Token Budgets ──
    max_context_tokens: int = 8192

    # ── OS Integration (Phase 7) ──
    os_bridge_url: str = "http://host.docker.internal:8001"
    os_hotkey: str = "ctrl+space"
    os_model: str = "qwen2.5"  # Default, override with vision model in .env if available
    os_screenshot_quality: int = 70
    os_screenshot_width: int = 1024

    @property
    def is_development(self) -> bool:
        return self.env == Environment.DEVELOPMENT

    @property
    def is_production(self) -> bool:
        return self.env == Environment.PRODUCTION


class DevelopmentSettings(Settings):
    """Development-specific overrides."""

    api_debug: bool = True


class ProductionSettings(Settings):
    """Production-specific overrides."""

    api_debug: bool = False


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance, auto-selecting environment class."""
    base = Settings()
    if base.is_production:
        return ProductionSettings()
    return DevelopmentSettings()
