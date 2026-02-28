"""
models.py — SQLModel table definitions (ORM + Pydantic schema in one class).

Three tables:
  User          — authentication identity
  Session       — one focus/work interval tied to a user
  MetricSample  — downsampled vitals snapshot tied to a session

Design decision: SQLModel combines SQLAlchemy table definition with Pydantic
validation in a single class, reducing boilerplate. Fields typed Optional[X]
map to nullable DB columns and are excluded from required Pydantic validation.

Naming note: the ORM model is imported as `DBSession` in other modules to avoid
shadowing FastAPI's `Session` dependency or Python's built-in concepts.
"""

from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Field, SQLModel


class User(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    username: str = Field(index=True, unique=True)
    # TODO: enforce bcrypt hashing in auth.py before storing — never store plaintext
    hashed_password: str


class Session(SQLModel, table=True):  # noqa: A001  (shadows built-in, acceptable here)
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id")
    start_time: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    end_time: Optional[datetime] = None

    # Computed on session end by sessions.py
    average_stress: Optional[float] = None

    # TODO: define focus scoring algorithm (e.g., % of time in low-stress zone)
    focus_score: Optional[float] = None


class MetricSample(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    session_id: int = Field(foreign_key="session.id")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # Raw vitals from C++ binary
    pulse: Optional[float] = None
    breathing: Optional[float] = None

    # TODO: populated once the stress scoring algorithm is implemented in vitals_reader.py
    stress_score: Optional[float] = None
