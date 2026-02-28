"""
vitals_reader.py — Background thread that reads vitals from the C++ subprocess.

Architecture overview:
  The C++ binary (stub or real Presage SmartSpectra SDK) is spawned by main.py
  and its Popen handle is passed into start_background_threads(). This module
  runs two daemon threads:

  Thread 1 — stdout_reader_thread:
    Reads the C++ process's stdout line-by-line. Each line is a JSON object:
      {"pulse": 72.4, "breathing": 14.1, "timestamp": 1709123456.789}
    Parses it and updates the shared `latest_vitals` dict under a Lock.

  Thread 2 — _downsample_writer_thread:
    Wakes every DOWNSAMPLE_INTERVAL_SECONDS. If a session is active, reads
    the latest vitals snapshot and writes one MetricSample row to SQLite.
    This prevents flooding the DB with 1 row/second from the C++ binary.

Shared state contract (read by websocket.py and sessions.py):
  latest_vitals = {
    "pulse":        float | None,
    "breathing":    float | None,
    "stress_score": float | None,   # TODO: computed once algorithm exists
    "timestamp":    float | None,   # Unix epoch seconds
  }

Design decision: threading.Lock protects the shared dict. asyncio is not used
here because subprocess stdout reading is inherently blocking I/O and runs
cleanly in a daemon thread without the event loop.
"""

import json
import subprocess
import threading
import time
from datetime import datetime, timezone
from typing import Callable, Optional

from sqlmodel import Session as OrmSession

from .config import get_settings
from .database import engine
from .models import MetricSample

settings = get_settings()

# ── Shared state ───────────────────────────────────────────────────────────────

_lock = threading.Lock()

latest_vitals: dict = {
    "pulse": None,
    "breathing": None,
    "stress_score": None,  # TODO: compute from HRV / breathing patterns (see below)
    "timestamp": None,
}


def get_latest_vitals() -> dict:
    """Thread-safe snapshot of the most recent vitals. Called by websocket.py."""
    with _lock:
        return dict(latest_vitals)


# ── Internal helpers ───────────────────────────────────────────────────────────

def _update_vitals(raw: dict) -> None:
    """
    Parse one validated JSON dict from the C++ process and update shared state.
    Called from the reader thread — protected by _lock.
    """
    with _lock:
        latest_vitals["pulse"] = raw.get("pulse")
        latest_vitals["breathing"] = raw.get("breathing")
        latest_vitals["timestamp"] = raw.get("timestamp", time.time())

        # TODO: implement advanced stress scoring algorithm
        # Candidate approaches:
        #   - HRV (heart rate variability) computed from pulse interval history
        #   - Breathing rate deviation from a personal baseline
        #   - LF/HF ratio from frequency-domain HRV analysis
        #   - Combined weighted score normalised to 0–100
        # For now, stress_score is always None until an algorithm is wired in.
        latest_vitals["stress_score"] = None


# ── Thread 1: stdout reader ────────────────────────────────────────────────────

def stdout_reader_thread(proc: subprocess.Popen) -> None:
    """
    Daemon thread: reads stdout from the C++ binary line by line until EOF.
    Stops automatically when the C++ process exits or stdout is closed.

    The C++ binary MUST flush after every line (fflush(stdout)) or this
    readline() call will block indefinitely.
    """
    for line in iter(proc.stdout.readline, b""):
        line = line.strip()
        if not line:
            continue
        try:
            data = json.loads(line)
            _update_vitals(data)
        except json.JSONDecodeError:
            # Ignore malformed lines (e.g., C++ debug prints, SDK warnings)
            pass

    # The process exited — vitals will remain at their last known values.
    # TODO: add supervised restart logic with exponential backoff if the binary
    #       crashes unexpectedly (important for a real deployment).
    print("[vitals_reader] C++ process stdout closed — reader thread exiting.")


# ── Thread 2: downsampled DB writer ───────────────────────────────────────────

def _downsample_writer_thread(active_session_id_getter: Callable[[], Optional[int]]) -> None:
    """
    Daemon thread: every DOWNSAMPLE_INTERVAL_SECONDS, persist one MetricSample
    to SQLite if a session is currently active.

    `active_session_id_getter` is a zero-argument callable returning the
    current active session ID (int) or None. It is injected as a callable to
    avoid a circular import between this module and sessions.py.
    """
    while True:
        time.sleep(settings.downsample_interval_seconds)

        session_id = active_session_id_getter()
        if session_id is None:
            continue  # No active session — nothing to persist

        snapshot = get_latest_vitals()
        if snapshot["timestamp"] is None:
            continue  # C++ binary hasn't sent data yet

        sample = MetricSample(
            session_id=session_id,
            timestamp=datetime.fromtimestamp(snapshot["timestamp"], tz=timezone.utc),
            pulse=snapshot["pulse"],
            breathing=snapshot["breathing"],
            stress_score=snapshot["stress_score"],
        )
        with OrmSession(engine) as db:
            db.add(sample)
            db.commit()


# ── Public entry point ─────────────────────────────────────────────────────────

def start_background_threads(
    proc: subprocess.Popen,
    active_session_id_getter: Callable[[], Optional[int]],
) -> None:
    """
    Called from main.py lifespan after spawning the C++ process.
    Starts both daemon threads. They die automatically when the main process exits.
    """
    t1 = threading.Thread(
        target=stdout_reader_thread,
        args=(proc,),
        daemon=True,
        name="vitals-stdout-reader",
    )
    t2 = threading.Thread(
        target=_downsample_writer_thread,
        args=(active_session_id_getter,),
        daemon=True,
        name="vitals-db-downsampler",
    )
    t1.start()
    t2.start()
    print("[vitals_reader] Background threads started.")
