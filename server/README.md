# Server — FastAPI Backend

## Overview

Python FastAPI server that:
- Spawns the C++ vitals binary as a subprocess on startup.
- Reads its stdout in a background thread and maintains in-memory latest vitals.
- Persists downsampled `MetricSample` rows to SQLite during active sessions.
- Streams live vitals to the React frontend over WebSocket (`/ws`).
- Handles user authentication (JWT) and session lifecycle via REST endpoints.

---

## File-by-File Guide

| File | What it does |
|------|-------------|
| `app/main.py` | FastAPI app init, lifespan (spawn subprocess + start threads), router mounts, CORS. |
| `app/config.py` | Loads all settings from `.env` via `python-dotenv`. Call `get_settings()` everywhere. |
| `app/database.py` | SQLite engine, `create_db_and_tables()` called once on startup, `get_session()` FastAPI dependency. |
| `app/models.py` | SQLModel ORM models: `User`, `Session`, `MetricSample`. |
| `app/auth.py` | `create_access_token`, `decode_access_token`, `get_current_user` dependency, register/login routes. |
| `app/vitals_reader.py` | `stdout_reader_thread` + `_downsample_writer_thread`, shared `latest_vitals` dict with `threading.Lock`, `get_latest_vitals()` for WebSocket. |
| `app/websocket.py` | `/ws` WebSocket endpoint — sends `latest_vitals` JSON every second. |
| `app/sessions.py` | `/session/start`, `/session/end`, `/session/{id}` — session lifecycle, in-memory active session tracking. |
| `app/llm_feedback.py` | `/llm-feedback` stub — returns placeholder; full integration plan in module docstring. |

---

## How to Run

```bash
# From the project root (NotStressedWorking/)
cd server
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cd ..

# Make sure .env exists (copy from .env.example and edit)
cp .env.example .env

# Start server (auto-reloads on file changes)
uvicorn server.app.main:app --reload --host 0.0.0.0 --port 8000
```

Server starts at: `http://localhost:8000`  
Swagger UI: `http://localhost:8000/docs`  
WebSocket: `ws://localhost:8000/ws`

---

## Environment Variables

Defined in `.env` at the project root. See [../.env.example](../.env.example) for all options.

Key variables:

| Variable | Purpose |
|----------|---------|
| `SECRET_KEY` | JWT signing key. **Must be changed before any real deployment.** |
| `CPP_BINARY_PATH` | Path to the compiled C++ binary (`./cpp/vitals_stub` by default). |
| `DB_URL` | SQLAlchemy DB URL (`sqlite:///./biofeedback.db` by default). |
| `DOWNSAMPLE_INTERVAL_SECONDS` | DB write frequency during a session (default: 5s). |

---

## Key Design Decisions

- **`threading.Lock` over asyncio** for the vitals dict: subprocess stdout reading is blocking I/O, cleanest in a daemon thread.
- **SQLModel** combines SQLAlchemy table definition + Pydantic validation in one class — less boilerplate for a hackathon.
- **In-memory active session tracking** (`_active_sessions` dict in `sessions.py`): fast for a single-process demo; swap for Redis in production.
- **Graceful missing binary handling**: if the C++ binary is not compiled, the server still starts with all vitals as `null`. Good for frontend-only development.

---

## TODOs (tracked in source)

- Hash passwords with bcrypt in `auth.py`.
- Implement stress scoring algorithm in `vitals_reader.py`.
- Implement `focus_score` in `sessions.py`.
- Wire up LLM in `llm_feedback.py` (Modal or OpenAI).
- Replace in-memory session tracking with Redis.
- Add structured logging.
- Add test suite (pytest + httpx `TestClient`).
