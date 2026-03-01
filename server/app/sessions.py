"""
sessions.py — Pomodoro-style work session tracking.

Links users to time-boxed work sessions on specific tasks/subtasks.
The frontend drives the actual countdown timer; this module only records
start/end times so the user can review their work history.

Endpoints:
  POST /sessions/start            — start a new work session
  POST /sessions/{id}/complete    — mark session completed, record duration
  POST /sessions/{id}/abandon     — mark session abandoned (user quit early)
  GET  /sessions                  — list sessions (filter by ?task_record_id=N)

Design decision: status is stored as a plain string ("active"/"completed"/
"abandoned") rather than an Enum to keep SQLite schema simple and avoid
Alembic migrations for a hackathon.
"""

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from .auth import get_current_user
from .database import get_session
from .models import User, WorkSession

router = APIRouter(prefix="/sessions", tags=["sessions"])


# ── Request models ─────────────────────────────────────────────────────────────

class StartSessionRequest(BaseModel):
    task_record_id: int
    subtask_index: Optional[int] = None  # 0-based index into TaskAnalysis.subtasks


# ── Routes ─────────────────────────────────────────────────────────────────────

@router.post("/start", status_code=201)
def start_session(
    req: StartSessionRequest,
    db: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Start a new work session. Returns the session record with its ID."""
    session = WorkSession(
        task_record_id=req.task_record_id,
        user_id=current_user.id,
        subtask_index=req.subtask_index,
        started_at=datetime.now(timezone.utc),
        status="active",
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


@router.post("/{session_id}/complete")
def complete_session(
    session_id: int,
    db: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Mark a session as completed and record elapsed minutes."""
    session = db.get(WorkSession, session_id)
    if not session or session.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.status != "active":
        raise HTTPException(status_code=400, detail=f"Session is already '{session.status}'")

    now = datetime.now(timezone.utc)
    session.completed_at = now
    session.duration_minutes = max(1, int((now - session.started_at).total_seconds() / 60))
    session.status = "completed"
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


@router.post("/{session_id}/abandon")
def abandon_session(
    session_id: int,
    db: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Abandon an active session early."""
    session = db.get(WorkSession, session_id)
    if not session or session.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.status != "active":
        raise HTTPException(status_code=400, detail=f"Session is already '{session.status}'")

    now = datetime.now(timezone.utc)
    session.completed_at = now
    session.duration_minutes = max(0, int((now - session.started_at).total_seconds() / 60))
    session.status = "abandoned"
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


@router.get("/")
def list_sessions(
    task_record_id: Optional[int] = None,
    db: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """
    List all work sessions for the current user, most recent first.
    Pass ?task_record_id=N to filter by a specific task.
    """
    query = select(WorkSession).where(WorkSession.user_id == current_user.id)
    if task_record_id is not None:
        query = query.where(WorkSession.task_record_id == task_record_id)
    query = query.order_by(WorkSession.started_at.desc())
    return db.exec(query).all()
