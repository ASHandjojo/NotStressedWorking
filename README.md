# 🍅 Pomodorocculus — Smart To-Do List Maker and Tracker

> **HackIllinois 2026**  
> An OpenAI-powered productivity app: describe a project, set a deadline, and get an AI-generated task breakdown with a live adaptive Pomodoro timer. As you check off tasks, the schedule automatically recompresses to keep you on track.

---

## Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Quick Start](#quick-start)
4. [Environment Variables](#environment-variables)
5. [Backend API Reference](#backend-api-reference)
   - [Auth](#auth)
   - [Task Analysis](#task-analysis)
   - [Adaptive Scheduler](#adaptive-scheduler)
   - [Session Tracking](#session-tracking)
   - [Health](#health)
6. [Frontend](#frontend)
   - [Components](#components)
   - [API Client (`api.js`)](#api-client-apijs)
7. [Data Flow](#data-flow)
8. [Demo Mode](#demo-mode)

---

## Overview

Pomodorocculus combines an LLM task planner with a deterministic scheduling engine and a Pomodoro timer. The user types a project description, picks a deadline, and the system:

1. Calls OpenAI to decompose the project into ordered subtasks with time estimates.
2. Runs a deterministic crunch algorithm to fit the work into the available time window.
3. Returns a live schedule where checking off a task triggers a backend recalculation — compressing remaining tasks if needed and adjusting timer durations automatically.

---

## Architecture

```
┌──────────────────────────────────────────────────────┐
│  React Frontend  (CRA, port 3000)                    │
│                                                      │
│  App.js          — Pomodoro timer, MODES state       │
│  ToDoList.jsx    — prompt → plan → tick loop         │
│  api.js          — thin HTTP client                  │
└──────────────┬───────────────────────────────────────┘
               │  HTTP (localhost:8000)
┌──────────────▼──────────────────────────────────────┐
│  FastAPI Backend  (Uvicorn, port 8000)              │
│                                                     │
│  /tasks/analyze  → task_analyzer.py  (LLM layer)    │
│  /v1/plan        → scheduler.py      (LLM + math)   │
│  /v1/tick        → planner.py        (pure math)    │
│  /v1/replan      → scheduler.py      (LLM + math)   │
│  /auth/*         → auth.py           (static token) │
│  /sessions/*     → sessions.py       (SQLite)       │
└─────────────────────────────────────────────────────┘
```

**Two-layer scheduling design:**

| Layer | File | Responsibility |
|---|---|---|
| LLM Layer | `task_analyzer.py`, `scheduler.py` | Soft estimates: effort, cognitive load, procrastination risk |
| Deterministic Layer | `planner.py` | Hard constraints: available minutes, crunch compression, schedule order |

The LLM may never override the deterministic math — it only provides initial soft values.

---

## Quick Start

### Backend

```bash
# From repo root
python -m venv .venv
source .venv/bin/activate
pip install -r server/requirements.txt

# Copy and fill in your keys
cp server/.env.example server/.env   # set OPENAI_API_KEY and STATIC_TOKEN

.venv/bin/uvicorn server.app.main:app --reload --port 8000
```

Swagger UI: http://localhost:8000/docs

### Frontend

```bash
cd src
# Ensure src/.env exists with REACT_APP_API_TOKEN matching STATIC_TOKEN above
npm install
npm start
```

App: http://localhost:3000

---

## Environment Variables

### `server/.env`

| Variable | Description | Example |
|---|---|---|
| `OPENAI_API_KEY` | OpenAI API key | `sk-proj-...` |
| `STATIC_TOKEN` | Hardcoded Bearer token for all auth-gated endpoints | `X_sho4H...` |
| `SECRET_KEY` | JWT signing secret (legacy, not used in demo) | `dev-secret` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | JWT TTL (legacy) | `60` |
| `DB_URL` | SQLite path | `sqlite:///./notstressed.db` |

### `src/.env`

| Variable | Description |
|---|---|
| `REACT_APP_API_TOKEN` | Must match `STATIC_TOKEN` above — baked in at `npm start` |

---

## Backend API Reference

All endpoints served at `http://localhost:8000`. Interactive docs at `/docs`.

### Auth

Static-token auth — no registration required for the demo. All auth-gated endpoints expect:

```
Authorization: Bearer <STATIC_TOKEN>
```

| Method | Path | Auth | Description |
|---|---|---|---|
| `POST` | `/auth/register` | No | Create a user account (legacy, unused in demo) |
| `POST` | `/auth/login` | No | Exchange credentials for a JWT (legacy) |

---

### Task Analysis

| Method | Path | Auth | Description |
|---|---|---|---|
| `POST` | `/tasks/analyze` | ✅ Bearer | Analyze a task with the LLM — returns full plan, **not** saved to DB |
| `POST` | `/tasks/` | ✅ Bearer | Analyze + save to DB |
| `GET` | `/tasks/` | ✅ Bearer | List all saved tasks for current user |
| `GET` | `/tasks/{id}` | ✅ Bearer | Retrieve one saved task analysis |
| `DELETE` | `/tasks/{id}` | ✅ Bearer | Delete a saved task |

#### `POST /tasks/analyze` — request

```json
{
  "task_name": "Build a portfolio website with a contact form",
  "stress_level": 6,
  "tiredness_level": 3
}
```

#### `POST /tasks/analyze` — response (`TaskAnalysis`)

```json
{
  "complexity": "medium",
  "estimated_total_minutes": 180,
  "suggested_sessions": 4,
  "reasoning": "A portfolio site requires design, HTML/CSS, JS form logic, and deployment...",
  "subtasks": [
    {
      "title": "Design layout and color scheme",
      "description": "Sketch the page structure and choose fonts/colors.",
      "estimated_minutes": 30,
      "difficulty": "easy"
    }
  ],
  "timer_config": {
    "work_minutes": 1,
    "break_minutes": 1,
    "sessions_before_long_break": 3,
    "long_break_minutes": 1
  },
  "encouragement": "You've got the skills — a clean portfolio will open real doors!"
}
```

> **Note:** `timer_config` values are automatically scaled by ÷60 (demo mode) so timers run under 1 minute. See [Demo Mode](#demo-mode).

---

### Adaptive Scheduler

No auth required on these endpoints.

| Method | Path | Description |
|---|---|---|
| `POST` | `/v1/plan` | Create a deadline-aware plan from subtasks |
| `POST` | `/v1/tick` | Record task progress; triggers crunch if behind |
| `POST` | `/v1/replan` | Full LLM re-estimation for incomplete tasks |
| `GET` | `/v1/debug/state` | Dump in-memory plan state (dev only) |

---

#### `POST /v1/plan`

Builds the adaptive schedule. Calls the LLM for per-task effort estimates, then runs deterministic crunch if the total exceeds the available window.

**Request**

```json
{
  "tasks": [
    { "id": "t1", "description": "Design layout", "priority": 1 },
    { "id": "t2", "description": "Build HTML structure", "priority": 2 }
  ],
  "deadline": "2026-03-01T14:15:00",
  "current_time": "2026-03-01T09:15:00Z",
  "tiredness": 0.3,
  "stress": 0.3,
  "timer_config": { "work_minutes": 1, "break_minutes": 1, "sessions_before_long_break": 3, "long_break_minutes": 1 }
}
```

**Response (`PlanResponse`)**

```json
{
  "plan_id": "a1b2c3d4",
  "remaining_available_minutes": 4.2,
  "remaining_required_minutes": 3.8,
  "on_track": true,
  "schedule": [
    {
      "id": "t1",
      "description": "Design layout",
      "estimated_minutes": 2,
      "session_length_minutes": 2,
      "cognitive_load": 0.4,
      "procrastination_risk": 0.2,
      "was_compressed": false,
      "completed": false
    }
  ],
  "notes": ["On track — no compression needed."],
  "task_changes": [],
  "timer_config": { "work_minutes": 1, "break_minutes": 1, "sessions_before_long_break": 3, "long_break_minutes": 1 }
}
```

- `was_compressed: true` + `⚡` in UI means the task was shortened by crunch logic.
- `timer_config` is echoed back (or adjusted if crunch fired during planning).

---

#### `POST /v1/tick`

Call every time the user checks off a task. Recalculates feasibility from wall-clock time; if behind, proportionally compresses remaining tasks and timer durations.

**Request**

```json
{
  "task_id": "t1",
  "minutes_spent": 2,
  "completed": true,
  "current_time": "2026-03-01T09:17:00Z"
}
```

**Response (`TickResponse`)**

```json
{
  "remaining_available_minutes": 3.9,
  "remaining_required_minutes": 1.8,
  "on_track": true,
  "replan_needed": false,
  "adjustment_message": null,
  "schedule": [ ... ],
  "timer_config": { "work_minutes": 1, "break_minutes": 1, "sessions_before_long_break": 3, "long_break_minutes": 1 }
}
```

- `minutes_spent` is **analytics only** — never used for deadline math (prevents drift).
- If `replan_needed: true`, the gap is too large for compression alone → call `/v1/replan`.
- `timer_config` is returned with compressed values if crunch fired.

---

#### `POST /v1/replan`

Re-runs LLM estimation for all incomplete tasks with updated context (completed tasks, new tiredness/stress). The LLM may propose skipping or reformulating tasks.

**Request**

```json
{
  "current_time": "2026-03-01T09:20:00Z",
  "tiredness": 0.5,
  "stress": 0.6
}
```

**Response**: same shape as `PlanResponse` with `task_changes` populated:

```json
{
  "task_changes": [
    "SKIPPED 't4': low value given time constraint",
    "REFORMULATED 't3': 'Full test suite' → 'Smoke test critical paths only'"
  ]
}
```

---

### Session Tracking

Persists Pomodoro session start/end times to SQLite. Auth required.

| Method | Path | Description |
|---|---|---|
| `POST` | `/sessions/start` | Start a work session, returns session record with `id` |
| `POST` | `/sessions/{id}/complete` | Mark session complete, records duration |
| `POST` | `/sessions/{id}/abandon` | Mark session abandoned |
| `GET` | `/sessions/` | List sessions; filter with `?task_record_id=N` |

**Start request**

```json
{ "task_record_id": 42, "subtask_index": 0 }
```

---

### Health

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Liveness check; returns OpenAI key status |

```json
{ "status": "ok", "version": "0.2.0-hackathon", "openai_configured": true }
```

---

## Frontend

Single-page React app (CRA). No routing — everything lives on one screen.

### Components

#### `App.js`
- Owns the **Pomodoro timer** state: `mode` (`work` / `short` / `long`), `timeRemaining`, `isRunning`
- `MODES` is a reactive `useState` — updates automatically when `analysis.timer_config` arrives from the LLM
- `useEffect` watches `analysis`: rebuilds `MODES` durations and resets the visible timer whenever a new `timer_config` comes in
- Renders the **eye canvas** (`updateEye()`) — draws an arc proportional to time remaining; redraws on every `timeRemaining` change even when the timer is paused
- Renders `<ToDoList>` and passes two callbacks:
  - `onAnalysis` — stores full LLM analysis (including `timer_config`) in `App` state
  - `onTimerConfig` — patches only `timer_config` into existing analysis state (called on crunch)

#### `ToDoList.jsx`
Props: `{ onAnalysis, onTimerConfig }`

| State | Purpose |
|---|---|
| `prompt` | User's project description textarea |
| `deadline` | `datetime-local` input value |
| `schedule` | Array of `ScheduledTask` from backend; each extended with `done: bool` |
| `planSummary` | `{ on_track, remaining_available_minutes, remaining_required_minutes, notes }` |
| `timerConfig` | Local copy of current timer config for passing to `createPlan` and `tick` |
| `loading` / `loadingStep` | Spinner state with step label |
| `error` | Displayed as a red warning |

**`handleGenerate` flow:**
1. `analyzeTask(prompt)` → LLM subtask breakdown + `timer_config`
2. `onAnalysis(analysis)` → updates `App` state → `MODES` update → timer resets
3. `createPlan(subtasks, deadlineUTC, 0.3, 0.3, timerConfig)` → adaptive schedule
4. Schedule rendered as checkable task list with time estimates

**`handleToggle` flow (checkbox):**
1. Optimistic UI update (instant checkbox feel)
2. `tick(id, estimatedMinutes, completed)` → backend recalculates
3. Replace schedule with backend's authoritative version (completed tasks stay visible, struck through)
4. If `res.timer_config` present → `onTimerConfig(cfg)` → `App` `MODES` update → timer resets
5. Update summary banner with new `on_track` status and any crunch message
6. Roll back optimistic update on error

---

### API Client (`api.js`)

Base URL: `http://localhost:8000`  
Auth token: read from `process.env.REACT_APP_API_TOKEN` at build time.

| Function | Endpoint | Auth | Used by |
|---|---|---|---|
| `analyzeTask(taskName, stress?, tiredness?)` | `POST /tasks/analyze` | ✅ | `ToDoList` on Generate |
| `createPlan(tasks, deadline, tiredness, stress, timerConfig?)` | `POST /v1/plan` | No | `ToDoList` on Generate |
| `tick(taskId, minutesSpent, completed)` | `POST /v1/tick` | No | `ToDoList` on checkbox |
| `replan(tiredness, stress)` | `POST /v1/replan` | No | (available, not wired to UI yet) |
| `saveTask(taskName, stress, tiredness)` | `POST /tasks/` | ✅ | (available) |
| `listTasks()` | `GET /tasks/` | ✅ | (available) |
| `deleteTask(taskId)` | `DELETE /tasks/{id}` | ✅ | (available) |
| `startSession(taskRecordId, subtaskIndex?)` | `POST /sessions/start` | ✅ | (available) |
| `completeSession(sessionId)` | `POST /sessions/{id}/complete` | ✅ | (available) |
| `abandonSession(sessionId)` | `POST /sessions/{id}/abandon` | ✅ | (available) |
| `listSessions()` | `GET /sessions/` | ✅ | (available) |
| `debugState()` | `GET /v1/debug/state` | No | Dev debugging |
| `health()` | `GET /health` | No | Dev debugging |

---

## Data Flow

```
User types prompt + deadline
        │
        ▼
analyzeTask()  →  POST /tasks/analyze
        │         LLM: complexity, subtasks[], timer_config
        │
        ├──→  onAnalysis(analysis)
        │         App.js: MODES updated, timer reset
        │
        ▼
createPlan()   →  POST /v1/plan
                  LLM estimates effort per subtask
                  Deterministic: crunch if required > available
                  Returns: schedule[], on_track, timer_config
        │
        ▼
Schedule rendered as checkbox list
        │
User checks off task
        │
        ▼
tick()         →  POST /v1/tick
                  Deterministic: recompute available window
                  If behind: compress tasks + timer_config
                  Returns: updated schedule[], timer_config
        │
        ├──→  Schedule re-rendered (completed tasks stay, struck through)
        └──→  onTimerConfig(cfg) → App.js MODES update → timer reset
```

---

## Demo Mode

`DEMO_SCALE = 60` in `scheduler.py` compresses all time calculations so **1 real hour = 1 demo minute**. This allows demonstrating the full adaptive scheduling pipeline in ~5 minutes of real time.

| What scales | Where | How |
|---|---|---|
| Deadline window | `scheduler.py` `/v1/plan` | Gap divided by 60 before all math |
| LLM task estimates | `scheduler.py` `estimate_task_effort` | `available_minutes` passed to LLM is already compressed |
| Timer durations | `task_analyzer.py` `analyze_task` | `work/break/long_break` divided by 60, floored at 1 min |
| Crunch timer floors | `scheduler.py` `/v1/tick` | Min 1 min (down from 15/5/10) |
| Task time floors | `planner.py` | Min 1 min per task (down from 5) |

To disable demo mode for production: set `DEMO_SCALE = 1` in `scheduler.py` and remove the `_DEMO_SCALE` block in `task_analyzer.py`.

**Suggested demo input:**
- **Prompt:** `Build a working hackathon project: React frontend, FastAPI backend, REST API connecting them, and a devpost writeup`
- **Deadline:** 5 hours from now (= 5 demo minutes of adaptive scheduling)
 
