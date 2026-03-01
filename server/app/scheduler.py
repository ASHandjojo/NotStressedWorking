"""
scheduler.py — Adaptive deadline-aware scheduling engine.

Exposes:
  POST /v1/plan        — create a full plan from tasks + deadline + current state
  POST /v1/tick        — record progress, recompute feasibility, compress if needed
                         returns replan_needed=true when crunch alone can't save the plan
  POST /v1/replan      — LLM re-estimation for incomplete tasks only (preserves completed)
                         call when tick returns replan_needed=true
  GET  /v1/debug/state — inspect in-memory plan state

Two-layer architecture:
  ┌─────────────────────────────────────────────────────────────┐
  │  LLM Layer  (estimate_task_effort)                         │
  │  • Estimates effort in minutes per task                    │
  │  • Estimates cognitive_load and procrastination_risk       │
  │  • Output = soft suggestion fed into the deterministic     │
  │    layer as initial values. Never controls hard limits.    │
  ├─────────────────────────────────────────────────────────────┤
  │  Deterministic Layer  (planner.py)                        │
  │  • compute_remaining_available_minutes (wall-clock math)  │
  │  • compute_remaining_required_minutes (sum of estimates)  │
  │  • apply_crunch_logic (proportional compression)          │
  │  • generate_schedule (priority sort)                      │
  └─────────────────────────────────────────────────────────────┘

State policy:
  _state holds the live plan between /plan and /tick calls.
  minutes_spent (from /tick) is ANALYTICS ONLY — stored in _state["analytics"].
  Time calculations always use current_time provided in the request body.
  State is in-memory (lost on restart) — acceptable for hackathon.
"""

import json
import uuid
from datetime import datetime, timezone
from typing import Optional

import openai
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .config import get_settings
from .planner import (
    DEFAULT_SESSION_MINUTES,
    REPLAN_THRESHOLD,
    TaskState,
    apply_crunch_logic,
    compute_remaining_available_minutes,
    compute_remaining_required_minutes,
    generate_schedule,
)

settings = get_settings()
router = APIRouter(prefix="/v1", tags=["scheduler"])


# ── In-memory state ────────────────────────────────────────────────────────────
# Single global plan state — fine for hackathon single-user demo.
# For multi-user production: key by user_id or JWT sub claim.

_state: dict = {
    "plan_id": None,
    "tasks": [],         # list[TaskState] — source of truth for the current plan
    "deadline": None,    # ISO string — stored for /tick recalculations
    "tiredness": 0.0,
    "stress": 0.0,
    "analytics": {},     # task_id → cumulative minutes_spent (ANALYTICS ONLY)
}


# ── Pydantic models ────────────────────────────────────────────────────────────

class TaskInput(BaseModel):
    id: str
    description: str
    priority: int  # 1 = most important; higher int = lower priority


class PlanRequest(BaseModel):
    tasks: list[TaskInput]
    deadline: str       # ISO 8601, e.g. "2026-03-01T23:59:00"
    current_time: str   # ISO 8601 — client provides system time as ground truth
    tiredness: float    # 0.0 (fresh) – 1.0 (exhausted)
    stress: float       # 0.0 (calm)  – 1.0 (overwhelmed)


class ScheduledTask(BaseModel):
    id: str
    description: str
    estimated_minutes: int
    session_length_minutes: int
    cognitive_load: float
    procrastination_risk: float
    was_compressed: bool


class PlanResponse(BaseModel):
    plan_id: str
    remaining_available_minutes: float
    remaining_required_minutes: float
    on_track: bool
    schedule: list[ScheduledTask]
    notes: list[str]
    task_changes: list[str] = []  # populated by /replan when tasks are skipped or reformulated


class TickRequest(BaseModel):
    task_id: str
    minutes_spent: float  # ANALYTICS ONLY — never used for deadline math
    completed: bool
    current_time: str     # ISO 8601 — always use this as the time ground truth


class TickResponse(BaseModel):
    remaining_available_minutes: float
    remaining_required_minutes: float
    on_track: bool
    replan_needed: bool  # True when crunch can't fix the gap — call POST /v1/replan
    adjustment_message: Optional[str] = None
    schedule: list[ScheduledTask]


class ReplanRequest(BaseModel):
    current_time: str  # ISO 8601 — client provides system time as ground truth
    tiredness: float   # updated tiredness since last plan
    stress: float      # updated stress since last plan


# ── LLM Layer ──────────────────────────────────────────────────────────────────

def estimate_task_effort(
    tasks: list[TaskInput],
    deadline: str,
    current_time: str,
    tiredness: float,
    stress: float,
    available_minutes: float,
    completed_tasks: list[TaskState] | None = None,
    allow_task_changes: bool = False,
) -> dict[str, dict]:
    """
    LLM LAYER — ask the model for per-task effort estimates.

    This is intentionally isolated from all deadline math. The output is a dict
    of soft estimates that feeds INTO the deterministic layer as starting values.
    The deterministic layer (planner.py) may compress them — LLM never overrides that.

    When called from /replan with allow_task_changes=True, the LLM may also:
      - action="skip": mark a task as not worth doing given the time constraint
      - action="reformulate": propose a scoped-down description for a task
      - action="keep": no change (default)
    These are soft suggestions — surfaced to the frontend via task_changes in PlanResponse.

    When called from /plan, allow_task_changes=False so tasks are never silently dropped
    on the initial plan.

    Validation:
      - estimated_minutes floored at 5 (no zero-minute tasks)
      - cognitive_load and procrastination_risk clamped to [0.0, 1.0]
      - On any failure (API error, bad JSON, missing keys): returns {} so the
        deterministic layer falls back to DEFAULT_SESSION_MINUTES per task.

    Returns:
        {task_id: {estimated_minutes, cognitive_load, procrastination_risk,
                   action, new_description, skip_reason}}
    """
    if not settings.openai_api_key:
        return {}

    task_list = "\n".join(
        f"  - id={t.id!r}, priority={t.priority}, description={t.description!r}"
        for t in tasks
    )

    completed_section = ""
    if completed_tasks:
        completed_lines = "\n".join(
            f"  - id={t['id']!r}, description={t['description']!r}"
            for t in completed_tasks
        )
        completed_section = f"""

Already completed tasks (DO NOT estimate these — use them as context to adjust
remaining estimates. E.g. if a setup task is done, dependent tasks may be faster):
{completed_lines}"""

    if allow_task_changes:
        action_instruction = """
- action: one of "keep", "skip", or "reformulate".
  Use "skip" if the task is low-value given the time remaining and completing it
  would jeopardize higher-priority work. Use "reformulate" if the task can be
  meaningfully scoped down to fit the time constraint.
  Use "keep" in all other cases.
- new_description: (only when action="reformulate") a shorter, scoped-down version
  of the task description that is realistically completable in estimated_minutes.
- skip_reason: (only when action="skip") one sentence explaining why it should be dropped."""
        action_schema = '"action": "keep|skip|reformulate", "new_description": "<optional>", "skip_reason": "<optional>"'
    else:
        action_instruction = ""
        action_schema = '"action": "keep"'

    prompt = f"""You are a precise productivity estimator for students and developers.

Available productive minutes before deadline: {available_minutes:.0f}
Deadline: {deadline}
Current time: {current_time}
User state: tiredness={tiredness:.1f}/1.0, stress={stress:.1f}/1.0{completed_section}

Remaining tasks to estimate:
{task_list}

For EACH remaining task provide:
- estimated_minutes: realistic minutes to complete (integer, minimum 5).
  The SUM of all estimated_minutes must not exceed {available_minutes:.0f}.
  Account for what has already been completed above when estimating effort.{action_instruction}
- cognitive_load: 0.0 (routine) to 1.0 (requires deep focus)
- procrastination_risk: 0.0 (will start immediately) to 1.0 (likely to be avoided)

Return ONLY valid JSON, no markdown:
{{
  "estimates": [
    {{"id": "<task_id>", "estimated_minutes": <int>, {action_schema}, "cognitive_load": <float>, "procrastination_risk": <float>}},
    ...
  ]
}}"""

    try:
        client = openai.OpenAI(api_key=settings.openai_api_key)
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a structured productivity estimation assistant. "
                        "Respond ONLY with valid JSON matching the requested schema. "
                        "No markdown fences, no explanation."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,  # low temperature = more deterministic estimates
            response_format={"type": "json_object"},
        )
        raw = response.choices[0].message.content
        data = json.loads(raw)
        return {
            e["id"]: {
                "estimated_minutes": max(5, int(e["estimated_minutes"])),
                "cognitive_load": float(max(0.0, min(1.0, e["cognitive_load"]))),
                "procrastination_risk": float(max(0.0, min(1.0, e["procrastination_risk"]))),
                "action": e.get("action", "keep"),
                "new_description": e.get("new_description"),
                "skip_reason": e.get("skip_reason"),
            }
            for e in data.get("estimates", [])
            if "id" in e
        }
    except (openai.OpenAIError, json.JSONDecodeError, KeyError, ValueError, TypeError):
        # Graceful fallback — deterministic layer still runs with DEFAULT_SESSION_MINUTES
        return {}


# ── Helpers ────────────────────────────────────────────────────────────────────

def _parse_dt(iso: str) -> datetime:
    """Parse ISO 8601 string → timezone-aware datetime (assumes UTC if no tz given)."""
    dt = datetime.fromisoformat(iso)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _build_task_states(
    tasks: list[TaskInput],
    llm_estimates: dict[str, dict],
) -> list[TaskState]:
    """
    Merge TaskInput list + LLM estimates into TaskState dicts.
    Falls back to DEFAULT_SESSION_MINUTES / neutral values if LLM missed a task.
    """
    return [
        TaskState(
            id=t.id,
            description=t.description,
            priority=t.priority,
            estimated_minutes=llm_estimates.get(t.id, {}).get(
                "estimated_minutes", DEFAULT_SESSION_MINUTES
            ),
            cognitive_load=llm_estimates.get(t.id, {}).get("cognitive_load", 0.5),
            procrastination_risk=llm_estimates.get(t.id, {}).get(
                "procrastination_risk", 0.3
            ),
            completed=False,
            was_compressed=False,
        )
        for t in tasks
    ]


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.post("/plan", response_model=PlanResponse)
def create_plan(req: PlanRequest):
    """
    Create a deadline-aware adaptive plan.

    Execution order (matters for understanding the architecture):
      1. Parse current_time and deadline from request (client is ground truth).
      2. DETERMINISTIC: compute remaining_available_minutes.
      3. LLM LAYER: estimate effort per task (soft values, may be compressed later).
      4. Build TaskState list merging TaskInput + LLM estimates.
      5. DETERMINISTIC: apply_crunch_logic if required > available.
      6. DETERMINISTIC: generate_schedule (priority order).
      7. Persist to in-memory _state for /tick updates.

    No auth required on this endpoint — add Depends(get_current_user) if needed.
    """
    try:
        deadline_dt = _parse_dt(req.deadline)
        current_dt = _parse_dt(req.current_time)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"Invalid datetime: {exc}")

    # ── DETERMINISTIC: how much productive time is left
    remaining_available = compute_remaining_available_minutes(
        deadline_dt, current_dt, req.tiredness, req.stress
    )

    # ── LLM LAYER: soft effort estimates — feed into deterministic layer below
    llm_estimates = estimate_task_effort(
        tasks=req.tasks,
        deadline=req.deadline,
        current_time=req.current_time,
        tiredness=req.tiredness,
        stress=req.stress,
        available_minutes=remaining_available,
    )

    # ── Build task states (LLM estimates + defaults for any missing tasks)
    task_states = _build_task_states(req.tasks, llm_estimates)

    # ── DETERMINISTIC: compress if the plan doesn't fit
    task_states, crunch_notes = apply_crunch_logic(task_states, remaining_available)
    remaining_required = compute_remaining_required_minutes(task_states)

    notes: list[str] = []
    if remaining_available <= 0:
        notes.append("WARNING: Deadline has already passed.")
    elif crunch_notes:
        notes.extend(crunch_notes)
    else:
        notes.append("On track — no compression needed.")
    if not llm_estimates:
        notes.append(
            "LLM estimates unavailable — using default session lengths. "
            "Check OPENAI_API_KEY."
        )

    # ── DETERMINISTIC: build ordered schedule
    schedule = generate_schedule(task_states)

    # ── Persist state for /tick
    plan_id = str(uuid.uuid4())[:8]
    _state.update({
        "plan_id": plan_id,
        "tasks": task_states,
        "deadline": req.deadline,
        "tiredness": req.tiredness,
        "stress": req.stress,
        "analytics": {t.id: 0.0 for t in req.tasks},
    })

    return PlanResponse(
        plan_id=plan_id,
        remaining_available_minutes=remaining_available,
        remaining_required_minutes=remaining_required,
        on_track=remaining_required <= remaining_available,
        schedule=[ScheduledTask(**s) for s in schedule],
        notes=notes,
    )


@router.post("/tick", response_model=TickResponse)
def tick(req: TickRequest):
    """
    Record task progress and recompute schedule feasibility.

    KEY DESIGN DECISIONS:
      - Out-of-order execution is fully supported. Any task_id may be ticked or
        completed at any time regardless of its suggested_order in the schedule.
        The engine never blocks progress on a task because a higher-priority task
        is still incomplete.
      - minutes_spent → stored in analytics dict ONLY. Never touches time math.
      - remaining_available_minutes → ALWAYS recomputed from current_time vs deadline.
        This prevents drift from accumulated rounding errors or missed ticks.
      - If behind: deterministic crunch logic compresses the plan automatically.
      - If ahead: plan is returned unchanged (could extend sessions — future work).
    """
    if not _state["plan_id"]:
        raise HTTPException(
            status_code=400, detail="No active plan. Call POST /v1/plan first."
        )

    # ── Analytics: accumulate minutes_spent (never used for time calculations)
    _state["analytics"][req.task_id] = (
        _state["analytics"].get(req.task_id, 0.0) + req.minutes_spent
    )

    # ── Mark completed if reported
    for task in _state["tasks"]:
        if task["id"] == req.task_id:
            if req.completed:
                task["completed"] = True
            break

    # ── DETERMINISTIC: recompute from wall-clock current_time (not from analytics)
    try:
        current_dt = _parse_dt(req.current_time)
        deadline_dt = _parse_dt(_state["deadline"])
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"Invalid datetime: {exc}")

    remaining_available = compute_remaining_available_minutes(
        deadline_dt, current_dt, _state["tiredness"], _state["stress"]
    )
    remaining_required = compute_remaining_required_minutes(_state["tasks"])

    adjustment_message: Optional[str] = None
    replan_needed = False

    if remaining_required > remaining_available:
        # DETERMINISTIC: compress — LLM is not called here, this must be instant
        _state["tasks"], crunch_notes = apply_crunch_logic(
            _state["tasks"], remaining_available
        )
        remaining_required = compute_remaining_required_minutes(_state["tasks"])
        adjustment_message = (
            "Behind schedule — plan compressed: " + "; ".join(crunch_notes)
            if crunch_notes
            else "Behind schedule — all tasks shortened to fit remaining time."
        )

        # If crunch still leaves us structurally over budget, flag for LLM replan
        if remaining_available > 0 and remaining_required > remaining_available * REPLAN_THRESHOLD:
            replan_needed = True
            adjustment_message = (
                (adjustment_message or "") +
                " Plan is structurally infeasible — call POST /v1/replan to reassess."
            ).strip()

    schedule = generate_schedule(_state["tasks"])

    return TickResponse(
        remaining_available_minutes=remaining_available,
        remaining_required_minutes=remaining_required,
        on_track=remaining_required <= remaining_available,
        replan_needed=replan_needed,
        adjustment_message=adjustment_message,
        schedule=[ScheduledTask(**s) for s in schedule],
    )


@router.post("/replan", response_model=PlanResponse)
def replan(req: ReplanRequest):
    """
    Re-run LLM effort estimation for incomplete tasks only, then reapply deterministic
    crunch and scheduling. Completed tasks are preserved and excluded from re-estimation.

    Call this when POST /v1/tick returns replan_needed=true — it means the gap between
    required and available time is too large for compression alone to fix.  The LLM
    re-estimates with fresh context: updated tiredness/stress, new available window,
    and knowledge of what's already been completed.

    tiredness and stress in the request body update _state for future ticks.
    """
    if not _state["plan_id"]:
        raise HTTPException(
            status_code=400, detail="No active plan. Call POST /v1/plan first."
        )

    try:
        current_dt = _parse_dt(req.current_time)
        deadline_dt = _parse_dt(_state["deadline"])
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"Invalid datetime: {exc}")

    # Update tiredness/stress in state — affects all future tick calculations too
    _state["tiredness"] = req.tiredness
    _state["stress"] = req.stress

    # ── DETERMINISTIC: recompute available window with updated user state
    remaining_available = compute_remaining_available_minutes(
        deadline_dt, current_dt, req.tiredness, req.stress
    )

    # ── Build TaskInput list for INCOMPLETE tasks only — completed stay as-is
    incomplete_tasks = [
        TaskInput(id=t["id"], description=t["description"], priority=t["priority"])
        for t in _state["tasks"]
        if not t["completed"]
    ]

    if not incomplete_tasks:
        # Everything is done — return empty schedule
        return PlanResponse(
            plan_id=_state["plan_id"],
            remaining_available_minutes=remaining_available,
            remaining_required_minutes=0.0,
            on_track=True,
            schedule=[],
            notes=["All tasks completed."],
        )

    # ── LLM LAYER: re-estimate effort for incomplete tasks only,
    # passing completed tasks as context so the LLM can adjust estimates
    # based on what's already been done (e.g. setup done → impl faster).
    # allow_task_changes=True lets the LLM propose skipping or reformulating tasks.
    completed_count = len(_state["tasks"]) - len(incomplete_tasks)
    completed_tasks = [t for t in _state["tasks"] if t["completed"]]
    llm_estimates = estimate_task_effort(
        tasks=incomplete_tasks,
        deadline=_state["deadline"],
        current_time=req.current_time,
        tiredness=req.tiredness,
        stress=req.stress,
        available_minutes=remaining_available,
        completed_tasks=completed_tasks,
        allow_task_changes=True,
    )

    # ── Apply LLM-proposed task changes before rebuilding states
    task_changes: list[str] = []
    skipped_ids: set[str] = set()
    for t in incomplete_tasks:
        est = llm_estimates.get(t.id, {})
        action = est.get("action", "keep")
        if action == "skip":
            reason = est.get("skip_reason", "low value given time constraint")
            task_changes.append(f"SKIPPED '{t.id}': {reason}")
            skipped_ids.add(t.id)
        elif action == "reformulate" and est.get("new_description"):
            task_changes.append(
                f"REFORMULATED '{t.id}': '{t.description}' → '{est['new_description']}'"
            )
            t.description = est["new_description"]  # mutate in-place for TaskInput

    # Filter out skipped tasks; keep reformulated ones with updated descriptions
    active_tasks = [t for t in incomplete_tasks if t.id not in skipped_ids]

    # Mark skipped tasks as completed in state so they vanish from the schedule
    for task in _state["tasks"]:
        if task["id"] in skipped_ids:
            task["completed"] = True

    # ── Rebuild only the active (non-skipped) task states with fresh LLM estimates
    # Reset was_compressed so crunch logic can re-evaluate from scratch
    refreshed = [
        TaskState(
            id=t.id,
            description=t.description,  # may be reformulated above
            priority=t.priority,
            estimated_minutes=llm_estimates.get(t.id, {}).get(
                "estimated_minutes", DEFAULT_SESSION_MINUTES
            ),
            cognitive_load=llm_estimates.get(t.id, {}).get("cognitive_load", 0.5),
            procrastination_risk=llm_estimates.get(t.id, {}).get(
                "procrastination_risk", 0.3
            ),
            completed=False,
            was_compressed=False,
        )
        for t in active_tasks
    ]

    # Preserve completed tasks in state (already marked above)

    # ── DETERMINISTIC: compress and schedule
    refreshed, crunch_notes = apply_crunch_logic(refreshed, remaining_available)
    remaining_required = compute_remaining_required_minutes(refreshed)

    _state["tasks"] = completed_tasks + refreshed

    notes: list[str] = [f"Replan: {completed_count} task(s) already completed, {len(refreshed)} re-estimated, {len(skipped_ids)} skipped."]
    if crunch_notes:
        notes.extend(crunch_notes)
    else:
        notes.append("On track after replan — no compression needed.")
    if not llm_estimates:
        notes.append(
            "LLM estimates unavailable — using default session lengths. "
            "Check OPENAI_API_KEY."
        )

    schedule = generate_schedule(_state["tasks"])

    return PlanResponse(
        plan_id=_state["plan_id"],
        remaining_available_minutes=remaining_available,
        remaining_required_minutes=remaining_required,
        on_track=remaining_required <= remaining_available,
        schedule=[ScheduledTask(**s) for s in schedule],
        notes=notes,
        task_changes=task_changes,
    )


@router.get("/debug/state")
def debug_state():
    """Return current in-memory plan state. Useful during frontend development."""
    if not _state["plan_id"]:
        return {"message": "No active plan."}
    return {
        "plan_id": _state["plan_id"],
        "deadline": _state["deadline"],
        "tiredness": _state["tiredness"],
        "stress": _state["stress"],
        "tasks": _state["tasks"],
        "analytics": _state["analytics"],
    }
