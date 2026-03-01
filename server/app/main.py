"""
main.py — FastAPI application entry point.

── Startup / Shutdown Lifecycle ──────────────────────────────────────────────
  1. lifespan() runs on startup:
       a. create_db_and_tables()       — ensure SQLite schema exists (idempotent)
       b. subprocess.Popen(binary)     — spawn C++ stub ONLY if CPP_BINARY_PATH exists (dev mode)
       c. start_background_threads()   — always starts DB downsampler;
                                         also starts stdout reader if stub was spawned
  2. FastAPI serves requests:
       POST /auth/register             — create account          (auth.py)
       POST /auth/login                — get JWT token           (auth.py)
       POST /vitals/ingest             — receive vitals from iOS (vitals_ingest.py)
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

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .database import create_db_and_tables
from . import auth, tasks, sessions, scheduler

settings = get_settings()

# ── Lifespan

@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifespan: run setup before yield, cleanup after."""
    create_db_and_tables()
    print("[main] DB ready. NotStressed Task Complexity API is up.")
    if settings.openai_api_key:
        print("[main] OpenAI key: configured OK")
    else:
        print("[main] WARNING: OpenAI key missing -- set OPENAI_API_KEY in .env")

    yield  # server runs here

    print("[main] Shutting down.")


# ── App ────────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="NotStressed -- Task Complexity Estimator API",
    description=(
        "LLM-powered task planner. Submit a task name + optional stress/tiredness levels "
        "and receive a structured plan: complexity score, subtask breakdown, "
        "Pomodoro timer config, and encouragement."
    ),
    version="0.2.0-hackathon",
    lifespan=lifespan,
)

# CORS -- allow all in development
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
app.include_router(tasks.router)
app.include_router(sessions.router)
app.include_router(scheduler.router)


@app.get("/health", tags=["meta"])
def health():
    """Liveness check."""
    return {
        "status": "ok",
        "version": app.version,
        "openai_configured": bool(settings.openai_api_key),
    }
