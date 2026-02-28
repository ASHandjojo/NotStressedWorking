"""
config.py — Central settings loader.

Reads all configuration from environment variables (via .env loaded by python-dotenv).
A single Settings instance is created at module import time and shared across all
modules via get_settings().

Design decision: using a plain dataclass + python-dotenv rather than pydantic-settings
to keep the dependency surface minimal for hackathon speed. For production, migrate to
pydantic-settings for type validation and cleaner error messages on missing vars.
"""

import os
from dataclasses import dataclass

from dotenv import load_dotenv

# Load .env from the project root (two levels up from server/app/)
load_dotenv()


@dataclass
class Settings:
    # JWT signing secret — MUST be changed before any real deployment
    secret_key: str = os.getenv("SECRET_KEY", "dev-secret-key-change-me")

    # Path to the compiled C++ vitals binary (stub or real Presage SDK process)
    cpp_binary_path: str = os.getenv("CPP_BINARY_PATH", "./cpp/vitals_stub")

    # SQLAlchemy-compatible DB URL; SQLite for hackathon, Postgres for production
    db_url: str = os.getenv("DB_URL", "sqlite:///./biofeedback.db")

    # How often (seconds) a downsampled MetricSample row is written during a session
    downsample_interval_seconds: int = int(os.getenv("DOWNSAMPLE_INTERVAL_SECONDS", "5"))

    # JWT access token lifetime in minutes
    access_token_expire_minutes: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))

    # JWT signing algorithm — HS256 is fine for single-server; use RS256 for multi-service
    algorithm: str = "HS256"


# Module-level singleton — import and call get_settings() everywhere instead of
# reading os.environ directly so the config contract stays in one place.
_settings = Settings()


def get_settings() -> Settings:
    """Return the shared Settings instance."""
    return _settings
