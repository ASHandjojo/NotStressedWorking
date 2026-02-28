"""
sessions.py — Session lifecycle endpoints.

A "session" represents one focus/work interval for a user (like a Pomodoro round).
Vitals are sampled during the session by vitals_reader.py and summarised on end.

Endpoints:
  POST /session/start    — create and activate a new session
  POST /session/end      — close the active session, compute summary stats
  GET  /session/{id}     — retrieve a past session with all its MetricSamples

Active session tracking:
  _active_sessions is an in-memory dict { user_id: session_id }. It is used by
  vitals_reader.py (via get_active_session_id()) to know which session to attach
  MetricSample rows to.

  Design decision: in-memory is fine for a hackathon single-process demo.
  For production: persist active session state in Redis so it survives restarts
  and supports horizontal scaling.

TODO:
  - Persist _active_sessions to Redis.
  - Implement focus_score algorithm (e.g., % of time in low-stress zone).
  - Add session history endpoint: GET /session/history (paginated).
  - Enforce maximum session duration / auto-end on timeout.
"""

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from .auth import get_current_user
from .database import get_session
from .models import MetricSample
from .models import Session as DBSession
from .models import User

router = APIRouter(prefix="/session", tags=["session"])

# In-memory map: user_id → active session_id
# TODO: replace with Redis for production
_active_sessions: dict[int, int] = {}


def get_active_session_id() -> Optional[int]:
    """
    Returns the first active session ID found (any user).
    Called as a callable by vitals_reader.py downsampler.

    TODO: refine to support multiple concurrent users — pass user context
          into the downsampler so each user's vitals go to their own session.
    """
    if _active_sessions:
        return next(iter(_active_sessions.values()))
    return None


@router.post("/start", status_code=201)
def start_session(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
):
    """
    Start a new session for the authenticated user.
    Fails with 400 if the user already has an active session.
    """
    if current_user.id in _active_sessions:
        raise HTTPException(status_code=400, detail="You already have an active session")

    new_session = DBSession(user_id=current_user.id)
    db.add(new_session)
    db.commit()
    db.refresh(new_session)

    _active_sessions[current_user.id] = new_session.id
    return {"session_id": new_session.id, "start_time": new_session.start_time}


@router.post("/end")
def end_session(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
):
    """
    End the authenticated user's active session and compute a summary.

    Summary computed here:
      average_stress — mean of all MetricSample.stress_score values for the session.
                       Will be null until the stress algorithm is implemented.
      focus_score    — stub / always null until algorithm is defined.

    TODO: implement focus_score (e.g., proportion of samples below stress threshold).
    TODO: emit a session-end event over WebSocket so the frontend can react.
    """
    session_id = _active_sessions.pop(current_user.id, None)
    if session_id is None:
        raise HTTPException(status_code=400, detail="No active session to end")

    sess = db.get(DBSession, session_id)
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found in database")

    sess.end_time = datetime.now(timezone.utc)

    # Compute average stress from stored samples
    samples = db.exec(
        select(MetricSample).where(MetricSample.session_id == session_id)
    ).all()
    stress_values = [s.stress_score for s in samples if s.stress_score is not None]
    sess.average_stress = sum(stress_values) / len(stress_values) if stress_values else None

    # TODO: implement focus_score algorithm
    sess.focus_score = None

    db.add(sess)
    db.commit()
    db.refresh(sess)

    return {
        "session_id": sess.id,
        "start_time": sess.start_time,
        "end_time": sess.end_time,
        "duration_seconds": (sess.end_time - sess.start_time).total_seconds(),
        "average_stress": sess.average_stress,
        "focus_score": sess.focus_score,
        "sample_count": len(samples),
    }


@router.get("/{session_id}")
def get_session_detail(
    session_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
):
    """
    Retrieve a completed session and all its MetricSamples.
    Only the session owner can access it.
    """
    sess = db.get(DBSession, session_id)
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")
    if sess.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied — not your session")

    samples = db.exec(
        select(MetricSample).where(MetricSample.session_id == session_id)
    ).all()

    return {"session": sess, "samples": samples}
