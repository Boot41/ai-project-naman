from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

SERVER_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=SERVER_DIR / ".env", extra="ignore")

    env: Literal["development", "test", "production"] = "development"
    database_url: str = ""
    secret_key: str = ""
    google_api_key: str = ""
    google_genai_use_vertexai: bool = False
    ops_agent_base_url: str = "http://localhost:8010"
    # Ops-agent investigations can take time due to multi-stage LLM + retrieval flow.
    ops_agent_timeout_seconds: float = 480.0

    @property
    def effective_db_url(self) -> str:
        if not self.database_url:
            raise RuntimeError(
                "DATABASE_URL is not configured. Set it in server/.env or environment."
            )
        return self.database_url

    @property
    def jwt_secret(self) -> str:
        if not self.secret_key:
            raise RuntimeError(
                "SECRET_KEY is not configured. Set it in server/.env or environment."
            )
        return self.secret_key


@lru_cache
def get_settings() -> Settings:
    return Settings()
