"""
models.py — SQLModel table definitions (ORM + Pydantic schema in one class).

Three tables:
  User        — authentication identity
  TaskRecord  — one LLM-analysed task tied to a user; stores full analysis JSON
  WorkSession — one Pomodoro-style work round tied to a TaskRecord

Design decision: analysis_json stores the full TaskAnalysis as a serialised JSON
string rather than normalised columns. This keeps the schema simple and flexible —
if the LLM response schema evolves, we don't need a DB migration.
"""

from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Field, SQLModel


class User(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    username: str = Field(index=True, unique=True)
    # TODO: hash with bcrypt in auth.py — never store plaintext in production
    hashed_password: str


class TaskRecord(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id")

    # Input from the user
    task_name: str
    stress_level: Optional[int] = None    # 1–10, self-reported
    tiredness_level: Optional[int] = None  # 1–10, self-reported

    # Full TaskAnalysis serialised as JSON (see task_analyzer.py for schema)
    analysis_json: str

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


class WorkSession(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    task_record_id: int = Field(foreign_key="taskrecord.id")
    user_id: int = Field(foreign_key="user.id")

    # Which subtask within TaskAnalysis.subtasks (0-indexed). None = full task session.
    subtask_index: Optional[int] = None

    started_at: datetime
    completed_at: Optional[datetime] = None
    duration_minutes: Optional[int] = None  # computed on complete/abandon

    # "active" | "completed" | "abandoned"
    status: str = Field(default="active")
