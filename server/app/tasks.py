"""
tasks.py — Task analysis and persistence endpoints.

POST /tasks/analyze      — analyze a task with the LLM (no auth — instant preview)
POST /tasks              — analyze + save result to DB (requires auth)
GET  /tasks              — list all saved tasks for the current user (requires auth)
GET  /tasks/{id}         — retrieve one saved task with full analysis (requires auth)
DELETE /tasks/{id}       — delete a saved task (requires auth)

Design decision: /tasks/analyze is unauthenticated so the frontend can show an
instant AI-generated plan before the user registers. POST /tasks requires auth so
results are persisted to a named account and can be retrieved across devices.
"""

import json
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from .auth import get_current_user
from .config import get_settings
from .database import get_session
from .models import TaskRecord, User
from .task_analyzer import TaskAnalysis, analyze_task

settings = get_settings()
router = APIRouter(prefix="/tasks", tags=["tasks"])


# ── Shared request model ───────────────────────────────────────────────────────

class AnalyzeRequest(BaseModel):
    task_name: str
    stress_level: Optional[int] = None    # 1–10, self-reported by user
    tiredness_level: Optional[int] = None  # 1–10, self-reported by user


# ── Helper ─────────────────────────────────────────────────────────────────────

def _record_to_dict(record: TaskRecord) -> dict:
    """Serialise a TaskRecord row into a JSON-friendly dict with parsed analysis."""
    return {
        "id": record.id,
        "task_name": record.task_name,
        "stress_level": record.stress_level,
        "tiredness_level": record.tiredness_level,
        "created_at": record.created_at,
        "analysis": json.loads(record.analysis_json),
    }


# ── Routes ─────────────────────────────────────────────────────────────────────

@router.post("/analyze", response_model=TaskAnalysis)
def analyze_endpoint(
    req: AnalyzeRequest,
    current_user: User = Depends(get_current_user),
):
    """
    Analyze a task and return the structured plan.
    Result is NOT saved to the database — use POST /tasks/ to analyze and persist.
    Requires Bearer token (POST /auth/login to get one).

    Example request body:
      {
        "task_name": "Finish distributed systems assignment",
        "stress_level": 7,
        "tiredness_level": 4
      }
    """
    return analyze_task(
        task_name=req.task_name,
        stress_level=req.stress_level,
        tiredness_level=req.tiredness_level,
        api_key=settings.openai_api_key,
    )


@router.post("/", status_code=201)
def create_task(
    req: AnalyzeRequest,
    db: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """
    Analyze a task and save the result to the database.
    Returns the saved record with the full analysis embedded.
    Requires Bearer token (POST to /auth/login to get one).
    """
    analysis = analyze_task(
        task_name=req.task_name,
        stress_level=req.stress_level,
        tiredness_level=req.tiredness_level,
        api_key=settings.openai_api_key,
    )
    record = TaskRecord(
        user_id=current_user.id,
        task_name=req.task_name,
        stress_level=req.stress_level,
        tiredness_level=req.tiredness_level,
        analysis_json=analysis.model_dump_json(),
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return _record_to_dict(record)


@router.get("/")
def list_tasks(
    db: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """
    List all saved task analyses for the current user, most recent first.
    """
    records = db.exec(
        select(TaskRecord)
        .where(TaskRecord.user_id == current_user.id)
        .order_by(TaskRecord.created_at.desc())
    ).all()
    return [_record_to_dict(r) for r in records]


@router.get("/{task_id}")
def get_task(
    task_id: int,
    db: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Get a single saved task analysis by ID."""
    record = db.get(TaskRecord, task_id)
    if not record or record.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Task not found")
    return _record_to_dict(record)


@router.delete("/{task_id}", status_code=204)
def delete_task(
    task_id: int,
    db: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Delete a saved task analysis."""
    record = db.get(TaskRecord, task_id)
    if not record or record.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Task not found")
    db.delete(record)
    db.commit()
