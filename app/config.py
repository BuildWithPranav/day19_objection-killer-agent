from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration loaded from environment variables."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "development"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    public_base_url: str = "http://localhost:8000"
    database_path: Path = Path("./data/objection_killer.db")
    log_level: str = "INFO"

    rep_shared_token: SecretStr = Field(default=SecretStr("change-me-long-random-token"))

    stt_provider: Literal["deepgram", "mock"] = "deepgram"
    deepgram_api_key: SecretStr | None = None
    deepgram_model: str = "nova-2"
    deepgram_language: str = "en-US"

    llm_enabled: bool = False
    openai_compatible_base_url: str = "https://api.openai.com/v1"
    openai_compatible_api_key: SecretStr | None = None
    openai_compatible_model: str = "gpt-4o-mini"

    objection_debounce_seconds: int = 8
    min_objection_confidence: float = 0.62
    max_cards_per_objection: int = 3


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached application settings."""

    return Settings()
