# API Walkthrough — End-to-End Request Sequence

Complete curl walkthrough covering every endpoint, auth enforcement, the no-crunch
happy path, a crunch-only tick, and a structural overload that triggers a full LLM replan.

**Prerequisites:**
```bash
# Terminal 1 — start server
.venv/bin/uvicorn server.app.main:app --reload --port 8000

# Terminal 2 — run all curl commands below
```

---

## 1. Health Check

No auth required. Confirms server is up and OpenAI key is loaded.

```bash
curl -s http://localhost:8000/health | python3 -m json.tool
```
```json
{
    "status": "ok",
    "version": "0.2.0-hackathon",
    "openai_configured": true
}
```

---

## 2. Protected Endpoint Without a Token → 401

```bash
curl -s http://localhost:8000/tasks/ | python3 -m json.tool
```
```json
{
    "detail": "Not authenticated"
}
```

`/tasks/` and all task/session endpoints require a Bearer token.  
`/v1/plan`, `/v1/tick`, `/v1/replan` are intentionally open (scheduler is stateless per session).

---

## 3. Register + Login

```bash
curl -s -X POST http://localhost:8000/auth/register \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=maria&password=test123" | python3 -m json.tool
```
```json
{
    "message": "User registered",
    "user_id": 1
}
```

```bash
TOKEN=$(curl -s -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=maria&password=test123" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
echo "Token: $TOKEN"
```

---

## 4. Protected Endpoint With Token → 200

```bash
curl -s http://localhost:8000/tasks/ \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
```
```json
[]
```

---

## 5. Plan — Happy Path (No Crunch)

Deadline is 2 days away, user is fresh, tasks are small. LLM estimates fit
comfortably — no compression needed.

```bash
curl -s -X POST http://localhost:8000/v1/plan \
  -H "Content-Type: application/json" \
  -d '{
    "tasks": [
      {"id": "t1", "description": "Write project report intro", "priority": 1},
      {"id": "t2", "description": "Run and document experiments", "priority": 2},
      {"id": "t3", "description": "Fix lint warnings", "priority": 3}
    ],
    "deadline": "2026-03-02T23:59:00",
    "current_time": "2026-02-28T10:00:00",
    "tiredness": 0.1,
    "stress": 0.1
  }' | python3 -m json.tool
```

**Expected response highlights:**
```json
{
    "plan_id": "a1b2c3d4",
    "remaining_available_minutes": 1710.0,
    "remaining_required_minutes": 95,
    "on_track": true,
    "notes": ["On track — no compression needed."],
    "schedule": [
        {"id": "t1", "description": "Write project report intro", "estimated_minutes": 45, "was_compressed": false},
        {"id": "t2", "description": "Run and document experiments", "estimated_minutes": 35, "was_compressed": false},
        {"id": "t3", "description": "Fix lint warnings", "estimated_minutes": 15, "was_compressed": false}
    ]
}
```

`was_compressed: false` on all tasks — crunch logic ran but found no surplus.

---

## 6. Tick — Normal Progress (No Crunch Triggered)

Complete t3 out of order — it was lowest priority but done first. That's fine,
execution order is never enforced.

```bash
curl -s -X POST http://localhost:8000/v1/tick \
  -H "Content-Type: application/json" \
  -d '{
    "task_id": "t3",
    "minutes_spent": 12,
    "completed": true,
    "current_time": "2026-02-28T10:30:00"
  }' | python3 -m json.tool
```
```json
{
    "remaining_available_minutes": 1692.0,
    "remaining_required_minutes": 80,
    "on_track": true,
    "replan_needed": false,
    "adjustment_message": null,
    "schedule": [
        {"id": "t1", "description": "Write project report intro", "estimated_minutes": 45, "was_compressed": false},
        {"id": "t2", "description": "Run and document experiments", "estimated_minutes": 35, "was_compressed": false}
    ]
}
```

`t3` is gone from the schedule. `replan_needed: false`, no compression message.

---

## 7. Tick — Crunch Triggered (Behind But Recoverable)

Simulate falling badly behind: jump `current_time` forward by 20 hours without
completing anything. `remaining_required` now exceeds `remaining_available` —
crunch fires and proportionally compresses tasks.

```bash
curl -s -X POST http://localhost:8000/v1/tick \
  -H "Content-Type: application/json" \
  -d '{
    "task_id": "t1",
    "minutes_spent": 20,
    "completed": false,
    "current_time": "2026-03-02T06:00:00"
  }' | python3 -m json.tool
```
```json
{
    "remaining_available_minutes": 108.0,
    "remaining_required_minutes": 72,
    "on_track": true,
    "replan_needed": false,
    "adjustment_message": "Behind schedule — plan compressed: Task 't1' (priority 1) compressed 45→32 min; Task 't2' (priority 2) compressed 35→24 min",
    "schedule": [
        {"id": "t1", "estimated_minutes": 32, "was_compressed": true},
        {"id": "t2", "estimated_minutes": 24, "was_compressed": true}
    ]
}
```

Crunch reduced both tasks proportionally. `on_track: true` after compression.
`replan_needed: false` — math fixed it, no LLM needed.

---

## 8. Tick — Structural Overload → replan_needed: true

Jump time to near the deadline so even maximum compression can't bridge the gap
(`remaining_required > remaining_available × 1.5` after crunch).

```bash
curl -s -X POST http://localhost:8000/v1/tick \
  -H "Content-Type: application/json" \
  -d '{
    "task_id": "t1",
    "minutes_spent": 10,
    "completed": false,
    "current_time": "2026-03-02T22:30:00"
  }' | python3 -m json.tool
```
```json
{
    "remaining_available_minutes": 11.2,
    "remaining_required_minutes": 56,
    "on_track": false,
    "replan_needed": true,
    "adjustment_message": "Behind schedule — all tasks shortened to fit remaining time. Plan is structurally infeasible — call POST /v1/replan to reassess.",
    "schedule": [
        {"id": "t1", "estimated_minutes": 5, "was_compressed": true},
        {"id": "t2", "estimated_minutes": 5, "was_compressed": true}
    ]
}
```

`replan_needed: true` — surface this to the user.  
Frontend prompt: *"You're significantly behind. Want to reassess your plan?"*

---

## 9. Replan — LLM Re-estimates Incomplete Tasks

User confirms replan. Stress bumped to 0.8 (more overwhelmed now).
Only incomplete tasks are re-estimated — t3 (already completed) is preserved.

```bash
curl -s -X POST http://localhost:8000/v1/replan \
  -H "Content-Type: application/json" \
  -d '{
    "current_time": "2026-03-02T22:30:00",
    "tiredness": 0.7,
    "stress": 0.8
  }' | python3 -m json.tool
```
```json
{
    "plan_id": "a1b2c3d4",
    "remaining_available_minutes": 8.1,
    "remaining_required_minutes": 8,
    "on_track": true,
    "notes": [
        "Replan: 1 task(s) already completed, 2 re-estimated.",
        "On track after replan — no compression needed."
    ],
    "schedule": [
        {"id": "t1", "description": "Write project report intro", "estimated_minutes": 5, "was_compressed": false},
        {"id": "t2", "description": "Run and document experiments", "estimated_minutes": 3, "was_compressed": false}
    ]
}
```

LLM re-estimated with the tight window and high stress as context.
`plan_id` is unchanged — same session, not a new plan.
Updated `tiredness`/`stress` are saved to state and used in all future ticks.

---

## 10. Debug State

Inspect full in-memory state at any point. `analytics` tracks cumulative
`minutes_spent` per task — used for dashboards only, never for time math.

```bash
curl -s http://localhost:8000/v1/debug/state | python3 -m json.tool
```
```json
{
    "plan_id": "a1b2c3d4",
    "deadline": "2026-03-02T23:59:00",
    "tiredness": 0.7,
    "stress": 0.8,
    "tasks": ["..."],
    "analytics": {
        "t1": 42.0,
        "t2": 0.0,
        "t3": 12.0
    }
}
```

---

## Endpoint Summary

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/health` | ❌ | Server + OpenAI status |
| POST | `/auth/register` | ❌ | Create user account |
| POST | `/auth/login` | ❌ | Get JWT token |
| POST | `/tasks/analyze` | ✅ | LLM task complexity analysis (no save) |
| POST | `/tasks/` | ✅ | Analyze + save task to DB |
| GET | `/tasks/` | ✅ | List saved tasks |
| GET | `/tasks/{id}` | ✅ | Get single saved task |
| DELETE | `/tasks/{id}` | ✅ | Delete saved task |
| POST | `/sessions/start` | ✅ | Start a Pomodoro session |
| POST | `/sessions/{id}/complete` | ✅ | Complete a session |
| POST | `/sessions/{id}/abandon` | ✅ | Abandon a session |
| GET | `/sessions/` | ✅ | List sessions |
| POST | `/v1/plan` | ❌ | Create adaptive plan (LLM + math) |
| POST | `/v1/tick` | ❌ | Record progress, compress if needed |
| POST | `/v1/replan` | ❌ | LLM re-estimate incomplete tasks |
| GET | `/v1/debug/state` | ❌ | Dump in-memory plan state |

---

## Interactive Docs

All endpoints are also explorable via the auto-generated Swagger UI:

```
http://localhost:8000/docs
```
