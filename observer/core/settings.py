"""Configuration centralisée, lue depuis .env."""
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")

    ai_router_key: str = ""
    ai_router_openai_base_url: str = "https://router.hostinger.com/v1"
    ai_router_anthropic_base_url: str = "https://router.hostinger.com"
    model_planner: str = "claude-haiku-5.5"
    model_triage: str = "claude-haiku-5.5"
    model_investigator: str = "claude-sonnet-5.5-eu"
    model_judge: str = "claude-sonnet-5.5-eu"
    model_dev: str = "claude-haiku-5.5"
    llm_budget_usd: float = 5.0
    usd_per_credit: float = 0.01  # 5000 crédits = 50 $
    apify_budget_usd: float = 4.0
    tiktok_every_min: int = 60
    model_transcribe: str = "whisper-1-eu"
    model_embed: str = "text-embedding-3-small"

    x_bearer_token: str = ""
    twitterapi_io_key: str = ""
    youtube_api_key: str = ""
    apify_token: str = ""
    telegram_api_id: str = ""
    telegram_api_hash: str = ""
    bsky_handle: str = ""
    bsky_app_password: str = ""

    database_url: str = "postgresql+asyncpg://observer:observer@localhost:5442/observer"
    redis_url: str = "redis://localhost:6380/0"
    api_token: str = "change-me"
    pseudo_salt: str = "change-me"


@lru_cache
def settings() -> Settings:
    return Settings()
