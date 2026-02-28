"""
main.py — FastAPI application entry point.

── Startup / Shutdown Lifecycle ──────────────────────────────────────────────
  1. lifespan() runs on startup:
       a. create_db_and_tables()       — ensure SQLite schema exists (idempotent)
       b. subprocess.Popen(binary)     — spawn the C++ vitals binary
       c. start_background_threads()   — start stdout reader + DB downsampler
  2. FastAPI serves requests:
       POST /auth/register             — create account          (auth.py)
       POST /auth/login                — get JWT token           (auth.py)
       POST /session/start             — begin a focus session   (sessions.py)
       POST /session/end               — end session + summary   (sessions.py)
       GET  /session/{id}              — retrieve past session   (sessions.py)
       POST /llm-feedback              — LLM stub                (llm_feedback.py)
       WS   /ws                        — live vitals stream      (websocket.py)
       GET  /health                    — liveness check
       GET  /docs                      — auto-generated Swagger UI
  3. lifespan() shutdown:
       — Terminate the C++ subprocess gracefully (SIGTERM, then wait 5s)

── Design Decisions ──────────────────────────────────────────────────────────
  - asynccontextmanager lifespan (not deprecated @app.on_event handlers).
  - subprocess stdout=PIPE so the Python reader thread can consume it line by line.
  - stderr=subprocess.DEVNULL avoids stderr blocking the process;
    TODO: redirect stderr to a rotating log file in production.
  - CORS allow_origins=["*"] is fine for a local hackathon demo;
    TODO: restrict to your frontend's origin before any deployment.
  - If the C++ binary is not compiled yet, the server still starts cleanly
    and all vitals fields will be null — safe for frontend development.
"""

import subprocess
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .database import create_db_and_tables
from .sessions import get_active_session_id
from .vitals_reader import start_background_threads
from . import auth, llm_feedback, sessions, websocket

settings = get_settings()

# Global handle to the C++ subprocess — kept here for shutdown cleanup
_cpp_process: subprocess.Popen | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifespan: startup before yield, shutdown after yield."""
    global _cpp_process

    # ── STARTUP ──────────────────────────────────────────────────────────────
    create_db_and_tables()
    print(f"[main] DB ready. Spawning C++ binary: {settings.cpp_binary_path}")

    try:
        _cpp_process = subprocess.Popen(
            [settings.cpp_binary_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,  # TODO: pipe to log file in production
        )
        print(f"[main] C++ process started (PID {_cpp_process.pid})")
        start_background_threads(_cpp_process, get_active_session_id)
    except FileNotFoundError:
        # Binary not compiled yet — server still starts, vitals will be null.
        # This is expected during frontend-only development.
        print(
            f"[main] WARNING: C++ binary not found at '{settings.cpp_binary_path}'. "
            "Vitals will be null. See cpp/README.md to compile the stub.",
            file=sys.stderr,
        )

    yield  # ← server runs here

    # ── SHUTDOWN ─────────────────────────────────────────────────────────────
    if _cpp_process and _cpp_process.poll() is None:
        _cpp_process.terminate()
        try:
            _cpp_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            _cpp_process.kill()
        print("[main] C++ process terminated.")


# ── App ────────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="NotStressed — Biofeedback Productivity API",
    description=(
        "Gamified biofeedback server. Streams live vitals from a C++ camera process "
        "over WebSocket, persists downsampled data to SQLite, and manages user sessions."
    ),
    version="0.1.0-hackathon",
    lifespan=lifespan,
)

# CORS — allow all origins in development so any local frontend can connect
# TODO: restrict allow_origins to your frontend URL before any deployment
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ────────────────────────────────────────────────────────────────────
app.include_router(auth.router)
app.include_router(sessions.router)
app.include_router(llm_feedback.router)
app.include_router(websocket.router)


@app.get("/health", tags=["meta"])
def health():
    """Liveness check — returns 200 when the server is up."""
    return {"status": "ok", "version": app.version}
