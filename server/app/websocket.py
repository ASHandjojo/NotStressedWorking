"""
websocket.py — WebSocket endpoint that streams live vitals to connected clients.

Endpoint:  ws://localhost:8000/ws

Message shape (JSON sent every ~1 second):
  {
    "pulse":        float | null,
    "breathing":    float | null,
    "stress_score": float | null,
    "timestamp":    float | null    ← Unix epoch seconds
  }

This shape is the contract your React teammate should program against.
Fields are null until the C++ binary starts sending data or until the
stress algorithm is implemented.

Design decision: a single global endpoint is sufficient for a hackathon
(one active user at a time in a demo setting). For a multi-user production
system, maintain a ConnectionManager with a set of active WebSocket objects
and broadcast to all / route to per-user channels.

TODO:
  - Add JWT authentication on connect (pass token as ?token= query param).
  - Add per-session or per-user rooms via a ConnectionManager.
  - Emit structured error events (e.g., {"event": "binary_not_running"}).
"""

import asyncio
import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from .vitals_reader import get_latest_vitals

router = APIRouter(tags=["websocket"])

# Push interval in seconds — matches the C++ binary's 1/sec output rate.
# Increase this if the client only needs lower-frequency updates.
SEND_INTERVAL_SECONDS = 1.0


@router.websocket("/ws")
async def vitals_websocket(websocket: WebSocket):
    """
    Accept a WebSocket connection and stream the latest vitals until the client
    disconnects or an unrecoverable error occurs.

    The `get_latest_vitals()` call is non-blocking (reads from an in-memory dict),
    so the asyncio event loop is never held up by I/O here.
    """
    await websocket.accept()
    try:
        while True:
            vitals = get_latest_vitals()
            await websocket.send_text(json.dumps(vitals))
            await asyncio.sleep(SEND_INTERVAL_SECONDS)
    except WebSocketDisconnect:
        # Client closed the connection cleanly — nothing to clean up
        pass
    except Exception as e:
        # Unexpected error — attempt a clean close before propagating
        # TODO: replace print with structured logger (e.g., structlog or logging)
        print(f"[websocket] Unexpected error: {e}")
        try:
            await websocket.close(code=1011, reason=str(e))
        except Exception:
            pass
