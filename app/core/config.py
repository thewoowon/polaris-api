from functools import lru_cache

from pydantic import AnyHttpUrl, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # --- App ---
    PROJECT_NAME: str = "Polaris API"
    API_V1_STR: str = "/api/v1"
    DEBUG: bool = False
    SQL_ECHO: bool = False  # SQLAlchemy statement logging; separate from FastAPI DEBUG

    # --- Database ---
    # Async SQLAlchemy URL, e.g. postgresql+asyncpg://user:pass@host:5432/db
    DATABASE_URL: str = Field(..., description="SQLAlchemy async DB URL")

    # --- Security ---
    JWT_SECRET_KEY: str = Field(..., description="Signing key for JWTs")
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # --- CORS ---
    BACKEND_CORS_ORIGINS: list[AnyHttpUrl] = []

    # --- LLM (classifier + reply polish) ---
    OPENAI_API_KEY: str = ""  # empty → fall back to StubClassifier
    OPENAI_CLASSIFIER_MODEL: str = "gpt-5.4-mini"
    # template | llm — `llm` polishes the template via OPENAI_CLASSIFIER_MODEL.
    # Stays "template" by default so cost is explicit.
    REPLY_GENERATOR: str = "template"

    # --- Notifications ---
    # ConsoleNotifier always fires. Slack fires too when webhook URL is set.
    NOTIFY_SLACK_WEBHOOK_URL: str = ""
    # Fire a notification when the policy action for a review resolves to
    # one of these (comma-separated). "*" → all actions.
    NOTIFY_POLICY_ACTIONS: str = "create_issue,route_to_human"
    # Also fire when a reply draft gets published.
    NOTIFY_ON_PUBLISH: bool = False

    # --- Google OAuth (operator login) ---
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    GOOGLE_REDIRECT_URI: str = "http://localhost:3000/auth/callback/google"
    GOOGLE_ALLOWED_DOMAINS: str = ""  # comma-separated Workspace domains; empty = allow all

    # --- Review ingestion worker ---
    # Only enable in ONE uvicorn worker to avoid duplicate ingestion.
    INGESTION_ENABLED: bool = False
    INGESTION_INTERVAL_SEC: int = 60
    INGESTION_SOURCES: str = "synthetic"  # comma-separated; only "synthetic" known right now

    # After each ingested review, optionally run classifier + policy engine
    # inline. Draft generation stays manual (blueprint §20 — no auto-publish
    # without an explicit operator action).
    INGESTION_AUTO_PIPELINE: bool = False
    INGESTION_AUTO_CLASSIFIER: str = "stub"  # stub | openai

    # Google Play source (via google-play-scraper — public pages, no key).
    INGESTION_GOOGLE_PLAY_APP_ID: str = ""  # e.g. com.kakao.talk
    INGESTION_GOOGLE_PLAY_LANG: str = "ko"
    INGESTION_GOOGLE_PLAY_COUNTRY: str = "kr"
    INGESTION_GOOGLE_PLAY_COUNT: int = 20

    # App Store source (via iTunes RSS — no key, ~50/page).
    INGESTION_APP_STORE_APP_ID: str = ""  # numeric app id
    INGESTION_APP_STORE_COUNTRY: str = "kr"

    @property
    def sync_database_url(self) -> str:
        """Swap the async driver for psycopg3 so Alembic / sync engines can use it."""
        if "+asyncpg" in self.DATABASE_URL:
            return self.DATABASE_URL.replace("+asyncpg", "+psycopg")
        if "+psycopg" in self.DATABASE_URL:
            return self.DATABASE_URL
        # bare postgresql:// — let SQLAlchemy pick the default; but prefer psycopg v3 explicitly.
        return self.DATABASE_URL.replace("postgresql://", "postgresql+psycopg://", 1)


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
