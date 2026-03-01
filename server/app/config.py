"""
config.py — Central settings loader.

Reads all configuration from environment variables (via .env loaded by python-dotenv).
A single Settings instance is created at module import time and shared across all
modules via get_settings().

Required .env variables:
  OPENAI_API_KEY   — your OpenAI key (platform.openai.com/api-keys)
  SECRET_KEY       — random string for JWT signing

Optional .env variables:
  DB_URL                      — SQLAlchemy URL (default: sqlite:///./notstressed.db)
  ACCESS_TOKEN_EXPIRE_MINUTES — JWT lifetime (default: 60)
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

    # SQLAlchemy-compatible DB URL; SQLite for hackathon, Postgres for production
    db_url: str = os.getenv("DB_URL", "sqlite:///./notstressed.db")

    # JWT access token lifetime in minutes
    access_token_expire_minutes: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))

    # JWT signing algorithm — HS256 is fine for single-server; use RS256 for multi-service
    algorithm: str = "HS256"

    # OpenAI API key — get yours at https://platform.openai.com/api-keys
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")


# Module-level singleton — import and call get_settings() everywhere instead of
# reading os.environ directly so the config contract stays in one place.
_settings = Settings()


def get_settings() -> Settings:
    """Return the shared Settings instance."""
    return _settings
