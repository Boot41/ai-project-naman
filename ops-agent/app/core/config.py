from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

OPS_AGENT_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=OPS_AGENT_DIR / ".env", extra="ignore")

    app_name: str = "ops-agent"
    model_name: str = "gemini-2.5-flash"
    google_api_key: str = ""

    @property
    def required_google_api_key(self) -> str:
        key = self.google_api_key.strip()
        if not key:
            raise RuntimeError(
                "GOOGLE_API_KEY is not configured in ops-agent/.env or environment."
            )
        return key


@lru_cache
def get_settings() -> Settings:
    return Settings()
