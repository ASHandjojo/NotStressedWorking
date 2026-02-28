# NotStressed — Gamified Biofeedback Productivity Tool

> **HackIllinois 2026**  
> A real-time biofeedback system that turns your physiological signals into a gamified focus experience.

---

## Table of Contents

1. [System Architecture](#system-architecture)
2. [Data Flow](#data-flow)
3. [Layer Responsibilities](#layer-responsibilities)
4. [Project Structure](#project-structure)
5. [WebSocket Contract (for frontend team)](#websocket-contract)
6. [REST API Reference](#rest-api-reference)
7. [How to Run](#how-to-run)
8. [How to Compile the C++ Stub](#how-to-compile-the-c-stub)
9. [How Real Presage SDK Replaces the Stub](#how-real-presage-sdk-replaces-the-stub)
10. [Environment Variables](#environment-variables)
11. [Future Steps / TODOs](#future-steps--todos)

---

## System Architecture

```
┌────────────────────────────────────────────────────────────┐
│                        User's Machine                      │
│                                                            │
│  ┌──────────────┐   stdout (JSON)   ┌───────────────────┐  │
│  │  C++ binary  │ ────────────────► │  FastAPI server   │  │
│  │ (vitals_stub │                   │  (Python)         │  │
│  │  or Presage  │                   │                   │  │
│  │  SDK)        │                   │  ┌─────────────┐  │  │
│  └──────────────┘                   │  │  SQLite DB  │  │  │
│                                     │  └─────────────┘  │  │
│                                     │         │         │  │
│                                     │  WebSocket /ws    │  │
│                                     └─────────┼─────────┘  │
│                                               │            │
│                                    ┌──────────▼─────────┐  │
│                                    │   React Frontend   │  │
│                                    │                    │  │
│                                    └────────────────────┘  │
└────────────────────────────────────────────────────────────┘
```

---

## Data Flow

```
[Camera / Presage SDK]
        │
        │  C++ process writes one JSON line/sec to stdout:
        │  {"pulse": 72.4, "breathing": 14.1, "timestamp": 1709123456.789}
        ▼
[vitals_reader.py — stdout_reader_thread]
        │
        │  Parses JSON → updates `latest_vitals` dict (protected by threading.Lock)
        │
        ├──► Every DOWNSAMPLE_INTERVAL_SECONDS (default 5s):
        │       Writes MetricSample row to SQLite (only during active session)
        │
        └──► On every WebSocket tick (1s):
                Reads latest_vitals → sends JSON to connected React client

[React Frontend — WebSocket client]
        │
        │  Receives vitals JSON every ~1s
        │  Drives UI: pulse display, breathing display, stress indicator, timer
        │
        └──► REST calls for auth and session lifecycle
```

---

## Layer Responsibilities

### `cpp/` — Vitals Source Process

| File | Purpose |
|------|---------|
| `vitals_binary_stub.cpp` | **Development stub.** Outputs random-valued vitals JSON every second. Replace with real Presage SmartSpectra SDK calls. |

- **Responsibility:** produce a continuous stream of vitals JSON on stdout.
- **Contract with Python:** one JSON object per line, newline-terminated, flushed immediately (`fflush`).
- **Does not know** about Python, HTTP, or the database.

---

### `server/` — FastAPI Backend

| File | Responsibility |
|------|---------------|
| `app/config.py` | Load all settings from `.env`. Single source of truth for config. |
| `app/database.py` | SQLite engine, table creation, session dependency. |
| `app/models.py` | ORM + Pydantic models: `User`, `Session`, `MetricSample`. |
| `app/auth.py` | JWT creation/verification, register/login endpoints, `get_current_user` dependency. |
| `app/vitals_reader.py` | Spawn C++ binary, read stdout, update shared `latest_vitals`, downsample to DB. |
| `app/websocket.py` | `/ws` WebSocket endpoint — broadcasts `latest_vitals` every second. |
| `app/sessions.py` | `/session/start`, `/session/end`, `/session/{id}` — session lifecycle. |
| `app/llm_feedback.py` | `/llm-feedback` — stub returning placeholder; integration plan in module docstring. |
| `app/main.py` | FastAPI app init, lifespan (subprocess spawn + thread start), router mounts. |

---

### React Frontend (teammate's code)

- Connects to `ws://localhost:8000/ws` to receive live vitals.
- Calls REST endpoints for auth, session management, and (future) LLM feedback.
- Drives the gamified timer and UI.

---

## Project Structure

```
NotStressedWorking/
├── .env                        ← gitignored — your local secrets
├── .env.example                ← committed — documents required env vars
│
├── server/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py             ← FastAPI entry point + lifespan
│   │   ├── config.py           ← settings loaded from .env
│   │   ├── database.py         ← SQLite engine + table creation
│   │   ├── models.py           ← User, Session, MetricSample
│   │   ├── auth.py             ← JWT auth + register/login routes
│   │   ├── vitals_reader.py    ← subprocess stdout reader + DB downsampler
│   │   ├── websocket.py        ← /ws WebSocket endpoint
│   │   ├── sessions.py         ← /session/* endpoints
│   │   └── llm_feedback.py     ← /llm-feedback stub
│   ├── requirements.txt
│   └── README.md
│
├── cpp/
│   ├── vitals_binary_stub.cpp  ← simulates Presage SDK output
│   └── README.md
│
└── README.md                   ← this file
```

---

## WebSocket Contract

> **For the frontend team:** connect to `ws://localhost:8000/ws`

The server pushes one JSON message per second:

```json
{
  "pulse":        72.4,
  "breathing":    14.1,
  "stress_score": null,
  "timestamp":    1709123456.789
}
```

| Field | Type | Notes |
|-------|------|-------|
| `pulse` | `number \| null` | Heart rate in bpm. `null` until C++ binary is running. |
| `breathing` | `number \| null` | Breathing rate in breaths/min. `null` until binary is running. |
| `stress_score` | `number \| null` | Always `null` for now — will be `0–100` once algorithm is implemented. |
| `timestamp` | `number \| null` | Unix epoch seconds (float). Matches the C++ binary's clock. |

**Reconnection:** the server does not send a goodbye frame; implement auto-reconnect with backoff on the client side.

---

## REST API Reference

Interactive docs available at `http://localhost:8000/docs` once the server is running.

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET`  | `/health` | — | Liveness check |
| `POST` | `/auth/register` | — | Create account (form: `username`, `password`) |
| `POST` | `/auth/login` | — | Get JWT token (form: `username`, `password`) |
| `POST` | `/session/start` | Bearer | Begin a focus session |
| `POST` | `/session/end` | Bearer | End session + get summary |
| `GET` | `/session/{id}` | Bearer | Get session + all MetricSamples |
| `POST` | `/llm-feedback` | Bearer | LLM feedback (stub) — body: `{"session_id": N}` |
| `WS` | `/ws` | — | Live vitals stream |

---

## How to Run

### 1 — Compile the C++ stub (first time only)

```bash
cd cpp
g++ -O2 -o vitals_stub vitals_binary_stub.cpp
# Test it manually:
./vitals_stub   # should print JSON every second
cd ..
```

### 2 — Set up the Python environment

```bash
cd server
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3 — Configure environment

```bash
# Back in the project root:
cp .env.example .env
# Edit .env — at minimum change SECRET_KEY
```

### 4 — Start the server

```bash
# From the project root:
uvicorn server.app.main:app --reload --host 0.0.0.0 --port 8000
```

The server will:
- Create `biofeedback.db` (SQLite) on first run.
- Spawn `./cpp/vitals_stub` automatically.
- Print `[main] C++ process started` in the console.
- Serve the API at `http://localhost:8000`.
- Serve interactive docs at `http://localhost:8000/docs`.

---

## How to Compile the C++ Stub

See [cpp/README.md](cpp/README.md) for detailed instructions and Presage SDK swap-in guide.

---

## How Real Presage SDK Replaces the Stub

The stub and the real SDK binary have the **same interface**: write JSON to stdout, flush after each line. The Python server does not change at all.

Steps:
1. Integrate the Presage SmartSpectra SDK into a C++ project (replace the `[STUB]` sections in `vitals_binary_stub.cpp`).
2. Compile the new binary.
3. Update `CPP_BINARY_PATH` in `.env` to point to the new binary.
4. Restart the server.

See [cpp/README.md](cpp/README.md) and [cpp/vitals_binary_stub.cpp](cpp/vitals_binary_stub.cpp) for the exact SDK call mapping.

---

## Environment Variables

See [.env.example](.env.example) for the full list with descriptions.

| Variable | Default | Description |
|----------|---------|-------------|
| `SECRET_KEY` | `dev-secret-key-change-me` | JWT signing secret. **Change before any deployment.** |
| `CPP_BINARY_PATH` | `./cpp/vitals_stub` | Path to the compiled vitals binary. |
| `DB_URL` | `sqlite:///./biofeedback.db` | SQLAlchemy DB URL. |
| `DOWNSAMPLE_INTERVAL_SECONDS` | `5` | How often a MetricSample row is written to DB. |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `60` | JWT access token lifetime. |

---

## Future Steps / TODOs

These are tracked as `TODO` comments throughout the codebase. Summary:

### Security
- [ ] **Hash passwords** with bcrypt (`passlib`) in `auth.py` before storing.
- [ ] Add refresh token support (short-lived access + long-lived refresh pair).
- [ ] Rate-limit the `/auth/login` endpoint.
- [ ] Restrict CORS `allow_origins` in `main.py` to the frontend's domain.

### Vitals & Stress
- [ ] **Implement stress scoring algorithm** in `vitals_reader.py`:
  - HRV from pulse interval history
  - Breathing rate deviation from personal baseline
  - LF/HF ratio (frequency-domain HRV)
- [ ] Swap stub binary for real **Presage SmartSpectra SDK** binary.
- [ ] Add supervised restart logic if the C++ process crashes.

### Sessions & Gamification
- [ ] Implement `focus_score` algorithm in `sessions.py`.
- [ ] Persist active session state to Redis for crash recovery.
- [ ] Add session history endpoint (`GET /session/history`).
- [ ] Define game mechanics: scoring, streaks, achievements.

### LLM Feedback
- [ ] Wire up LLM in `llm_feedback.py` (Modal or OpenAI — see module docstring).
- [ ] Stream LLM response back to client.

### Infrastructure
- [ ] Add structured logging (structlog or Python's `logging` module).
- [ ] Add proper test suite (pytest + httpx TestClient).
- [ ] Containerise with Docker for demo deployment.
- [ ] Replace SQLite with PostgreSQL for multi-user production.
