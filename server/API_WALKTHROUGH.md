# API Walkthrough — Sample Request Workflow

A complete end-to-end sequence demonstrating every endpoint.  
Run these in order from the project root with the server already running.

**Prerequisites:**
```bash
# Terminal 1 — server running
uvicorn server.app.main:app --reload --host 0.0.0.0 --port 8000

# Terminal 2 — send requests
```

---

## 1. Health Check
No authentication required. Confirms the server is up.

```bash
curl http://localhost:8000/health
```
```json
{"status": "ok", "version": "0.1.0-hackathon"}
```

---

## 2. Register a User

```bash
curl -s -X POST http://localhost:8000/auth/register \
  -d "username=maria&password=test123"
```
```json
{"message": "User registered", "user_id": 1}
```

---

## 3. Login and Capture the Token

```bash
TOKEN=$(curl -s -X POST http://localhost:8000/auth/login \
  -d "username=maria&password=test123" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

echo $TOKEN
```
```
eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```
> The `$TOKEN` variable is used in all subsequent requests.

---

## 4. Start a Focus Session

```bash
curl -s -X POST http://localhost:8000/session/start \
  -H "Authorization: Bearer $TOKEN"
```
```json
{"session_id": 1, "start_time": "2026-02-28T18:00:00"}
```

---

## 5. Read Live Vitals over WebSocket

Listens for 3 consecutive vitals messages from the C++ binary (one per second):

```bash
python3 -c "
import asyncio, websockets, json

async def check():
    async with websockets.connect('ws://localhost:8000/ws') as ws:
        for _ in range(3):
            msg = await ws.recv()
            print(json.dumps(json.loads(msg), indent=2))

asyncio.run(check())
"
```
```json
{
  "pulse": 84.0,
  "breathing": 13.0,
  "stress_score": null,
  "timestamp": 1709140856.123
}
{
  "pulse": 77.0,
  "breathing": 15.0,
  "stress_score": null,
  "timestamp": 1709140857.124
}
{
  "pulse": 91.0,
  "breathing": 12.0,
  "stress_score": null,
  "timestamp": 1709140858.125
}
```
> `stress_score` is `null` until the scoring algorithm is implemented in `vitals_reader.py`.

---

## 6. End the Session

```bash
curl -s -X POST http://localhost:8000/session/end \
  -H "Authorization: Bearer $TOKEN"
```
```json
{
  "session_id": 1,
  "start_time": "2026-02-28T18:00:00",
  "end_time": "2026-02-28T18:05:00",
  "duration_seconds": 300.0,
  "average_stress": null,
  "focus_score": null,
  "sample_count": 60
}
```
> `average_stress` and `focus_score` are `null` until their algorithms are implemented.

---

## 7. Retrieve a Past Session

Replace `1` with the `session_id` returned in step 4.

```bash
curl -s http://localhost:8000/session/1 \
  -H "Authorization: Bearer $TOKEN"
```
```json
{
  "session": {
    "id": 1,
    "user_id": 1,
    "start_time": "2026-02-28T18:00:00",
    "end_time": "2026-02-28T18:05:00",
    "average_stress": null,
    "focus_score": null
  },
  "samples": [
    {"id": 1, "session_id": 1, "timestamp": "...", "pulse": 84.0, "breathing": 13.0, "stress_score": null},
    ...
  ]
}
```

---

## 8. LLM Feedback (Stub)

```bash
curl -s -X POST http://localhost:8000/llm-feedback \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"session_id": 1}'
```
```json
{
  "session_id": 1,
  "user": "maria",
  "message": "LLM feedback not yet implemented",
  "status": "stub"
}
```

---

## Interactive Docs

All endpoints are also explorable via the auto-generated Swagger UI:

```
http://localhost:8000/docs
```
