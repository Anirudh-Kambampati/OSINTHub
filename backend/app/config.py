"""Runtime configuration. All secrets are read server-side from the environment only."""

from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="OSINT_", extra="ignore")

    database_url: str = "sqlite+aiosqlite:///./osint.db"

    environment: str = "development"  # "production" enables secure cookies and strict checks
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]
    log_json: bool = False

    # Authentication. The first account created becomes an admin; after that, only admins
    # can add users unless open registration is explicitly enabled.
    allow_registration: bool = False
    session_ttl_hours: int = 72
    cookie_secure: bool | None = None  # defaults to True in production

    # Job queue / worker. With run_worker_in_api the API process also executes investigations
    # (single-node default). In production run `python -m app.worker` separately and set it false.
    run_worker_in_api: bool = True
    worker_poll_seconds: float = 2.0
    worker_heartbeat_timeout_seconds: int = 300
    # Delete investigations older than this many days (None = keep forever).
    retention_days: int | None = None

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
    login_rate_limit_per_minute: int = 10

    # Optional official-API credentials. Connectors that need them report
    # REQUIRES_AUTHENTICATION when they are absent; nothing is bypassed.
    github_token: SecretStr | None = None
    reddit_client_id: SecretStr | None = None
    reddit_client_secret: SecretStr | None = None
    youtube_api_key: SecretStr | None = None
    x_bearer_token: SecretStr | None = None
    brave_search_api_key: SecretStr | None = None


    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production"

    @property
    def secure_cookies(self) -> bool:
        return self.is_production if self.cookie_secure is None else self.cookie_secure


@lru_cache
def get_settings() -> Settings:
    return Settings()
