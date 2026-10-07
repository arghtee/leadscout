from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration, read from environment variables (see .env.example)."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore", env_ignore_empty=True)

    database_url: str = "sqlite:///./leadscout.db"
    redis_url: str = "redis://localhost:6379/0"
    log_level: str = "INFO"

    google_places_api_key: SecretStr | None = None
    companies_house_api_key: SecretStr | None = None
    meta_graph_token: SecretStr | None = None

    rocketreach_mcp_url: str = "https://mcp.rocketreach.co/mcp"
    rocketreach_auth: SecretStr | None = None
    min_credit_balance: int | None = None
    max_credits_per_run: int | None = None
    max_contacts_per_company: int = Field(default=2, ge=1)
    lookup_poll_timeout_s: int = Field(default=120, ge=1)

    llm_provider: str = "anthropic"
    llm_api_key: SecretStr | None = None

    google_oauth_client_id: str | None = None
    google_oauth_client_secret: SecretStr | None = None

    sender_postal_address: str | None = None
    max_spend_per_run: float | None = None
    daily_send_cap: int = Field(default=30, ge=0)


@lru_cache
def get_settings() -> Settings:
    return Settings()
