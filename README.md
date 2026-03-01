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
[iPhone — SmartSpectra Swift SDK]
        │
        │  VitalsStreamer.swift POSTs every ~1 second:
        │  POST /vitals/ingest
        │  {"pulse": 72.4, "breathing": 14.1, "timestamp": 1709123456.789}
        ▼
[vitals_ingest.py — POST /vitals/ingest]
        │
        │  Updates `latest_vitals` dict (protected by threading.Lock)
        │
        ├──► Every DOWNSAMPLE_INTERVAL_SECONDS (default 5s):
        │       vitals_reader._downsample_writer_thread writes MetricSample to SQLite
        │
        └──► On every WebSocket tick (~1s):
                websocket.py reads latest_vitals → sends JSON to React frontend

[React Frontend — WebSocket client]
        │
        │  Receives vitals JSON every ~1s
        │  Drives UI: pulse display, breathing display, stress indicator, timer
        │
        └──► REST calls for auth and session lifecycle

[C++ Stub — dev mode only, optional]
        If ./cpp/vitals_stub exists at startup, the server spawns it as a subprocess
        and reads its stdout — same JSON format, same pipeline. Use when iPhone
        is unavailable for local development.
```

---

## Layer Responsibilities

### `swift/` — iOS Vitals Source (Primary)

| File | Purpose |
|------|--------|
| `NotStressedApp.swift` | `@main` iOS app entry point. |
| `ContentView.swift` | SwiftUI root view embedding `SmartSpectraView` and starting `VitalsStreamer`. |
| `VitalsStreamer.swift` | Reads `sdk.metricsBuffer` every second, POSTs JSON to `POST /vitals/ingest`. |

- **Requires:** physical iPhone (iOS 15+), Xcode 15+, API key from physiology.presagetech.com.
- **Contract with server:** `POST /vitals/ingest` with `{"pulse", "breathing", "timestamp"}`.
- **Does not know** about WebSocket, React, or SQLite.

---

### `cpp/` — Dev Stub (Optional, offline development)

| File | Purpose |
|------|--------|
| `vitals_binary_stub.cpp` | **Development-only stub.** Simulates vitals via stdout when iPhone is unavailable. Auto-detected by server at startup. |

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
| `POST` | `/auth/login` | — | Get JWT token (form: `username`, `password`) || `POST` | `/vitals/ingest` | — | Receive vitals from iOS app (called by `VitalsStreamer.swift`) || `POST` | `/session/start` | Bearer | Begin a focus session |
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

## How to Set Up the Swift iOS App

See [swift/README.md](swift/README.md) for full Xcode setup instructions. Summary:

1. Open Xcode → **File → New → Project** → iOS App
2. Add SmartSpectra via **File → Add Package Dependencies…**
   - URL: `https://github.com/Presage-Security/SmartSpectra` — Branch: `main`
3. Copy `swift/*.swift` files into your Xcode target
4. Add `NSCameraUsageDescription` to `Info.plist`
5. In `VitalsStreamer.swift`, set `SERVER_URL` to your Mac’s LAN IP and `SMARTSPECTRA_API_KEY`
6. Run on a **physical iPhone** (iOS 15+) — simulator is not supported

---

## How to Run the C++ Dev Stub (No iPhone)

Used when the iPhone is unavailable (server-only or React development).

```bash
cd cpp && g++ -O2 -o vitals_stub vitals_binary_stub.cpp && cd ..
```

The server auto-detects `CPP_BINARY_PATH` in `.env` at startup and spawns the stub.
Set `CPP_BINARY_PATH=./cpp/vitals_stub` (already the default).

---

## Environment Variables

See [.env.example](.env.example) for the full list with descriptions.

| Variable | Default | Description |
|----------|---------|-------------|
| `SECRET_KEY` | `dev-secret-key-change-me` | JWT signing secret. **Change before any deployment.** |
| `CPP_BINARY_PATH` | `./cpp/vitals_stub` | Path to the C++ dev stub binary (optional — only used if file exists). |
| `DB_URL` | `sqlite:///./biofeedback.db` | SQLAlchemy DB URL. |
| `DOWNSAMPLE_INTERVAL_SECONDS` | `5` | How often a MetricSample row is written to DB. |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `60` | JWT access token lifetime. |
| `SMARTSPECTRA_API_KEY` | `your-api-key-here` | Presage API key — set in `VitalsStreamer.swift` (not read by Python server). |

---

## Adaptive Scheduling Engine (`/v1`)

### What it does

Given a list of tasks, a deadline, and the user's current stress/tiredness level,
the engine produces a realistic, compressed work schedule and tracks whether the
user remains on pace as time passes.

### Two-layer architecture

```
┌─────────────────────────────────────────────────────────────┐
│  LLM Layer  (scheduler.py → estimate_task_effort)          │
│  • Estimates effort in minutes per task                    │
│  • Estimates cognitive_load (0–1) per task                 │
│  • Estimates procrastination_risk (0–1) per task           │
│  Output = SOFT SUGGESTION only. Never controls hard limits. │
├─────────────────────────────────────────────────────────────┤
│  Deterministic Layer  (planner.py)                        │
│  • Computes remaining_available_minutes from wall clock    │
│  • Computes remaining_required_minutes (sum of estimates)  │
│  • Applies crunch compression if required > available      │
│  • Generates priority-ordered schedule                     │
│  This layer owns ALL hard constraints.                     │
└─────────────────────────────────────────────────────────────┘
```

### Why `current_time` is required in every request

The server never derives the current time from accumulated `minutes_spent`.
Clock-based calculations accumulate drift when ticks are missed, delayed, or
batched. Instead, the client passes `current_time` (ISO 8601) in each request
and the server uses that as the single source of truth for all deadline math.

### Why `minutes_spent` is analytics-only

`POST /v1/tick` accepts `minutes_spent` but stores it only in an analytics
dict (visible at `GET /v1/debug/state`). It is never used to compute how much
time is left. That calculation always comes from `deadline − current_time`.

### Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/v1/plan` | Create a plan. LLM estimates effort; deterministic layer checks feasibility and compresses if needed. |
| `POST` | `/v1/tick` | Record progress. Recomputes schedule from wall clock. Returns `on_track` + compressed schedule if behind. |
| `GET`  | `/v1/debug/state` | Inspect in-memory plan state (tasks, analytics, deadline). |

### Example: POST /v1/plan

```json
{
  "tasks": [
    {"id": "t1", "description": "Write report intro", "priority": 1},
    {"id": "t2", "description": "Run experiments",    "priority": 2},
    {"id": "t3", "description": "Fix lint warnings",   "priority": 5}
  ],
  "deadline":     "2026-03-02T23:59:00",
  "current_time": "2026-03-01T10:00:00",
  "tiredness": 0.6,
  "stress": 0.4
}
```

Response includes `remaining_available_minutes`, `remaining_required_minutes`,
`on_track` (bool), `schedule` (ordered list with `session_length_minutes`,
`cognitive_load`, `procrastination_risk`, `was_compressed`), and `notes`.

---

## Future Steps / TODOs

### Security
- [ ] Hash passwords with bcrypt (`passlib`) in `auth.py`.
- [ ] Add refresh token support.
- [ ] Rate-limit `/auth/login`.
- [ ] Restrict CORS `allow_origins` to the frontend's domain.

### Scheduling Engine
- [ ] Persist plan state to Redis so it survives server restarts.
- [ ] Per-user plan state (currently single global — fine for demo).
- [ ] Call LLM on `/tick` to re-estimate remaining tasks when significantly behind.
- [ ] Extend session length when ahead of schedule.

### Infrastructure
- [ ] Add structured logging.
- [ ] Add pytest test suite for `planner.py` (pure functions — easy to test).
- [ ] Containerise with Docker.
- [ ] Replace SQLite with PostgreSQL for production.
