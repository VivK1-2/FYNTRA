from pathlib import Path
from typing import List, Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

INSECURE_API_KEYS = {"", "default_dev_key_change_me", "your_super_secret_api_key_here"}


class Settings(BaseSettings):
    PROJECT_NAME: str = "FYNTRA API"
    VERSION: str = "0.2.0"
    API_V1_STR: str = "/api/v1"
    ENVIRONMENT: str = "development"  # development | production

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/fyntra"

    # Auth: clients (the FYNTRA frontend/server) send this in the X-API-Key header.
    # Set to "disabled" ONLY for local development.
    API_KEY: str = "default_dev_key_change_me"

    # Admin panel. Empty = admin endpoints disabled. Use a long random value (openssl rand -hex 24).
    ADMIN_KEY: str = ""

    # CORS: comma separated list of allowed frontend origins
    CORS_ORIGINS: str = "http://localhost:3000"

    # SEC (must contain a real contact email, SEC blocks anonymous clients)
    SEC_USER_AGENT: str = Field(default="FYNTRA Research (contact@example.com)")
    SEC_API_BASE_URL: str = "https://data.sec.gov/api/xbrl/"

    # LLM (the model name lives ONLY here, in the backend; the frontend never sees it)
    LLM_BASE_URL: str = "https://api.scalemax.pro/token/v1"
    LLM_API_KEY: Optional[str] = None
    LLM_MODEL: str = "gpt-6-luna"
    LLM_FALLBACK_MODEL: str = ""  # optional second model on the same endpoint
    LLM_TIMEOUT_SECONDS: float = 60.0

    # Rate limiting (per client IP, per minute). 0 disables. LLM-backed/ingest routes get the stricter cap.
    RATE_LIMIT_PER_MINUTE: int = 120
    RATE_LIMIT_LLM_PER_MINUTE: int = 12

    # Storage (local volume on the VPS)
    STORAGE_DIR: str = "/data/filings"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @property
    def cors_origins_list(self) -> List[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @field_validator("STORAGE_DIR")
    @classmethod
    def _storage(cls, v: str) -> str:
        # A relative folder (./storage) is anchored to the backend folder, not to wherever uvicorn was
        # started from, so reports saved earlier are always found again.
        p = Path(v).expanduser()
        if not p.is_absolute():
            p = Path(__file__).resolve().parents[2] / p
        return str(p.resolve())

    @field_validator("ENVIRONMENT")
    @classmethod
    def _env(cls, v: str) -> str:
        return v.lower()

    def assert_production_safe(self) -> None:
        """Refuse to boot in production with unsafe settings."""
        if self.ENVIRONMENT != "production":
            return
        problems = []
        if self.API_KEY in INSECURE_API_KEYS or self.API_KEY == "disabled":
            problems.append("API_KEY must be set to a long random value")
        if "*" in self.cors_origins_list:
            problems.append("CORS_ORIGINS must not contain '*'")
        if "example.com" in self.SEC_USER_AGENT:
            problems.append("SEC_USER_AGENT must contain a real contact email")
        if self.ADMIN_KEY and len(self.ADMIN_KEY) < 16:
            problems.append("ADMIN_KEY must be at least 16 characters")
        if problems:
            raise RuntimeError("Unsafe production config: " + "; ".join(problems))


settings = Settings()
