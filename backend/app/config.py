"""Runtime configuration. All secrets are read server-side from the environment only."""

from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="OSINT_", extra="ignore")

    database_url: str = "sqlite+aiosqlite:///./osint.db"

    # Optional shared bearer token. When set, every /api request must present it.
    api_token: SecretStr | None = None
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    # Outbound HTTP behaviour
    user_agent: str = "OSINT-Console/0.1 (public-information research; respects robots.txt)"
    http_timeout: float = 12.0
    connector_timeout: float = 30.0
    max_html_bytes: int = 2_000_000
    max_document_bytes: int = 10_000_000
    max_image_bytes: int = 3_000_000

    # Investigation limits
    max_concurrent_investigations: int = 4
    max_pivot_websites: int = 3
    max_documents: int = 3
    create_rate_limit_per_minute: int = 10

    # Optional official-API credentials. Connectors that need them report
    # REQUIRES_AUTHENTICATION when they are absent; nothing is bypassed.
    github_token: SecretStr | None = None
    reddit_client_id: SecretStr | None = None
    reddit_client_secret: SecretStr | None = None
    youtube_api_key: SecretStr | None = None
    x_bearer_token: SecretStr | None = None
    brave_search_api_key: SecretStr | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
