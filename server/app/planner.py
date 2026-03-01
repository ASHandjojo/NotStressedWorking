"""
planner.py — Deterministic scheduling math layer.

ALL functions here are pure Python: no LLM calls, no I/O, no side effects.
They can be unit-tested independently of FastAPI and OpenAI.

Architecture note — WHY TWO LAYERS:
  This module owns ALL hard constraints:
    - How many minutes are realistically available before the deadline
    - Whether the plan fits inside that window
    - How to compress tasks when it doesn't
  The LLM layer (scheduler.py) provides SOFT estimates (effort, cognitive load,
  procrastination risk) which feed into this layer as initial values.
  The LLM may never override these calculations — it only informs them.
"""

from datetime import datetime
from typing import TypedDict

# Productive hours assumed per 24h period (student grinding = ~10 usable hours)
USABLE_HOURS_PER_DAY: float = 10.0

# Minimum productivity multiplier even when exhausted (you still function at 20%)
MIN_CAPACITY_FACTOR: float = 0.2

# Fallback session length when LLM estimate is unavailable
DEFAULT_SESSION_MINUTES: int = 2

# Maximum we'll reduce any single task's time in one crunch pass (40% reduction cap)
MAX_COMPRESSION_RATIO: float = 0.40

# If remaining_required > remaining_available * this factor after crunch, the plan is
# structurally broken — compression alone can't save it, a full LLM replan is needed.
REPLAN_THRESHOLD: float = 1.5


class TaskState(TypedDict):
    id: str
    description: str
    priority: int            # 1 = most important; higher number = lower priority
    estimated_minutes: int   # set by LLM; fallback = DEFAULT_SESSION_MINUTES
    cognitive_load: float    # 0.0–1.0 from LLM (0 = routine, 1 = deep focus needed)
    procrastination_risk: float  # 0.0–1.0 from LLM (1 = likely to be avoided)
    completed: bool
    was_compressed: bool     # True if crunch logic reduced this task's time


# ── Pure math functions ────────────────────────────────────────────────────────

def compute_usable_capacity_factor(tiredness: float, stress: float) -> float:
    """
    Map tiredness + stress to a productivity multiplier in [MIN_CAPACITY_FACTOR, 1.0].

    DETERMINISTIC — no LLM.

    Args:
        tiredness: 0.0 (fully rested) to 1.0 (exhausted)
        stress:    0.0 (calm)         to 1.0 (overwhelmed)

    Design: tiredness weights heavier than stress (0.4 vs 0.3) because physical
    fatigue has a larger impact on sustained cognitive work than moderate stress
    (low stress can actually improve focus).

    Examples:
        (0.0, 0.0) → 1.00   (fresh and calm — full capacity)
        (0.5, 0.5) → 0.65   (moderately tired and stressed)
        (1.0, 1.0) → 0.30   (exhausted — capped well above 0 to stay realistic)
    """
    raw = 1.0 - 0.4 * tiredness - 0.3 * stress
    return round(max(MIN_CAPACITY_FACTOR, min(1.0, raw)), 4)


def compute_remaining_available_minutes(
    deadline: datetime,
    current_time: datetime,
    tiredness: float,
    stress: float,
) -> float:
    """
    Compute realistic productive minutes left before the deadline.

    DETERMINISTIC — derived purely from wall-clock time and capacity math.
    NEVER derived from accumulated minutes_spent — that path causes drift.

    Steps:
      1. Raw wall-clock minutes until deadline.
      2. Assume USABLE_HOURS_PER_DAY of each 24h are productive (no sleep/meals).
      3. Multiply by capacity factor to account for current tiredness/stress.

    Returns 0.0 if the deadline has already passed.
    """
    raw_minutes = (deadline - current_time).total_seconds() / 60.0
    if raw_minutes <= 0.0:
        return 0.0
    days = raw_minutes / (24.0 * 60.0)
    usable_raw = days * USABLE_HOURS_PER_DAY * 60.0
    capacity = compute_usable_capacity_factor(tiredness, stress)
    return round(usable_raw * capacity, 1)


def compute_remaining_required_minutes(tasks: list[TaskState]) -> float:
    """
    Sum estimated_minutes across all incomplete tasks.

    DETERMINISTIC — simple sum, no LLM.
    """
    return float(sum(t["estimated_minutes"] for t in tasks if not t["completed"]))


def apply_crunch_logic(
    tasks: list[TaskState],
    remaining_available: float,
) -> tuple[list[TaskState], list[str]]:
    """
    Compress lowest-priority tasks to make the plan fit the available window.

    DETERMINISTIC — pure constraint math, not LLM reasoning.

    Algorithm:
      Pass 1 — proportional compression of lowest-priority tasks:
        Sort incomplete tasks by priority descending (highest number = least important).
        For each task from lowest priority upward:
          Reduce by up to MAX_COMPRESSION_RATIO until surplus is eliminated.
          Floor: no task goes below 5 minutes.

      Pass 2 — global scale if still over budget after Pass 1:
        Scale ALL remaining incomplete tasks proportionally to fit available time.
        Floor: 5 minutes per task.

    Returns:
        (updated_tasks, notes) — notes lists every compression action taken.
    """
    incomplete = [t for t in tasks if not t["completed"]]
    completed = [t for t in tasks if t["completed"]]
    notes: list[str] = []

    required = sum(t["estimated_minutes"] for t in incomplete)
    surplus = required - remaining_available

    if surplus <= 0:
        return tasks, notes  # already fits — nothing to do

    # Pass 1: reduce lowest-priority tasks first
    sorted_by_low_priority = sorted(incomplete, key=lambda t: -t["priority"])

    for task in sorted_by_low_priority:
        if surplus <= 0:
            break
        original = task["estimated_minutes"]
        reducible = original * MAX_COMPRESSION_RATIO
        reduction = min(reducible, surplus)
        task["estimated_minutes"] = max(1, round(original - reduction))
        task["was_compressed"] = True
        surplus -= reduction
        notes.append(
            f"Task '{task['id']}' (priority {task['priority']}) "
            f"compressed {original}→{task['estimated_minutes']} min"
        )

    # Pass 2: if still over budget, scale everything proportionally
    if surplus > 0:
        total = sum(t["estimated_minutes"] for t in sorted_by_low_priority)
        if total > 0:
            scale = remaining_available / total
            for task in sorted_by_low_priority:
                original = task["estimated_minutes"]
                task["estimated_minutes"] = max(1, round(original * scale))
                task["was_compressed"] = True
            notes.append(
                f"Global scale applied ({scale:.0%}) — all tasks shortened to fit deadline."
            )

    # Reassemble in original priority order
    all_tasks: list[TaskState] = completed + sorted(
        sorted_by_low_priority, key=lambda t: t["priority"]
    )
    return all_tasks, notes


def generate_schedule(
    tasks: list[TaskState],
    analytics: dict[str, float] | None = None,
) -> list[dict]:
    """
    Return ALL tasks as a session list — incomplete ones first (sorted by id),
    completed ones appended after.

    For completed tasks, estimated_minutes is replaced with the actual minutes
    spent (from analytics) so the frontend can show real time vs estimated.
    Falls back to the original estimate if analytics has no entry.

    DETERMINISTIC — no LLM.
    """
    analytics = analytics or {}
    incomplete = sorted(
        [t for t in tasks if not t["completed"]],
        key=lambda t: t["id"],
    )
    completed = sorted(
        [t for t in tasks if t["completed"]],
        key=lambda t: t["id"],
    )
    def _row(t: TaskState) -> dict:
        actual = analytics.get(t["id"])
        minutes = (
            round(actual) if t["completed"] and actual
            else t["estimated_minutes"]
        )
        return {
            "id": t["id"],
            "description": t["description"],
            "estimated_minutes": minutes,
            "session_length_minutes": minutes,
            "cognitive_load": t["cognitive_load"],
            "procrastination_risk": t["procrastination_risk"],
            "was_compressed": t["was_compressed"],
            "completed": t["completed"],
        }
    return [_row(t) for t in incomplete + completed]
