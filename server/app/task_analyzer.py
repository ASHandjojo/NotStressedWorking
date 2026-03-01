"""
task_analyzer.py — LLM-powered task complexity analysis.

Core function: analyze_task() sends a task description + optional user state
(stress level, tiredness level) to the OpenAI API and returns a fully structured
response containing:
  - overall complexity rating
  - total time estimate
  - number of suggested Pomodoro-style work sessions
  - concrete subtask breakdown
  - timer configuration tailored to the user's current state
  - an encouraging message

Design decisions:
  - Pydantic models here (not in models.py) because they are API response shapes,
    not DB table definitions. TaskRecord in models.py stores the analysis as
    serialised JSON so the schema can evolve without DB migrations.
  - openai>=1.40.0 required for client.beta.chat.completions.parse() which
    returns a typed Pydantic object directly, no manual JSON parsing needed.
  - Timer config adapts to stress/tiredness: high stress → shorter work blocks;
    calm state → longer deep work blocks (45–50 min).
"""

from typing import Literal, Optional

import openai
from fastapi import HTTPException
from pydantic import BaseModel, Field


# ── Response schema (also serves as the OpenAI structured output spec) ─────────

class Subtask(BaseModel):
    title: str = Field(description="Short action-oriented title, 3-8 words")
    description: str = Field(description="One sentence explaining what to do and why")
    estimated_minutes: int = Field(description="Realistic time estimate in minutes")
    difficulty: Literal["easy", "medium", "hard"]


class TimerConfig(BaseModel):
    work_minutes: int = Field(description="Length of one focused work block in minutes")
    break_minutes: int = Field(description="Short break length in minutes")
    sessions_before_long_break: int = Field(description="Work blocks before a long break")
    long_break_minutes: int = Field(description="Long break length in minutes")


class TaskAnalysis(BaseModel):
    complexity: Literal["low", "medium", "high", "very_high"]
    estimated_total_minutes: int = Field(
        description="Total realistic time estimate in minutes (including breaks), not optimistic"
    )
    suggested_sessions: int = Field(
        description="Number of focused work sessions (Pomodoro rounds) to complete the task"
    )
    reasoning: str = Field(
        description="2-3 sentences explaining the complexity estimate and suggested approach"
    )
    subtasks: list[Subtask] = Field(
        description="3-7 concrete, ordered, actionable steps to complete the main task"
    )
    timer_config: TimerConfig = Field(
        description="Pomodoro-style timer settings adapted to this task and the user's current state"
    )
    encouragement: str = Field(
        description="One sentence of genuine, specific encouragement for this particular task and user state"
    )


# ── Core function ──────────────────────────────────────────────────────────────

def analyze_task(
    task_name: str,
    stress_level: Optional[int],     # 1–10, or None if not provided
    tiredness_level: Optional[int],  # 1–10, or None if not provided
    api_key: str,
) -> TaskAnalysis:
    """
    Call OpenAI with a structured output schema and return a TaskAnalysis object.

    The timer_config is adapted based on stress/tiredness:
      - stress >= 7  → shorter blocks (20–25 min) with more breaks
      - stress <= 3  → longer deep-work blocks (45–50 min)
      - tiredness >= 7 → more rest, smaller subtasks, fewer sessions per day

    Raises:
      HTTPException 503  — API key missing or OpenAI service unavailable
      HTTPException 429  — OpenAI rate limit hit
      HTTPException 502  — unexpected OpenAI API error
    """
    if not api_key:
        raise HTTPException(
            status_code=503,
            detail=(
                "OpenAI API key is not configured. "
                "Add OPENAI_API_KEY=sk-... to your .env file."
            ),
        )

    # Build natural-language user context for the prompt
    context_parts: list[str] = []
    if stress_level is not None:
        context_parts.append(f"stress level {stress_level}/10")
    if tiredness_level is not None:
        context_parts.append(f"tiredness level {tiredness_level}/10")

    user_context = (
        f"The user currently reports: {', '.join(context_parts)}. "
        if context_parts
        else "No stress or tiredness data provided — assume a normal rested state. "
    )

    # Derive adaptive guidance to steer the LLM's timer recommendations
    state_guidance = ""
    if stress_level is not None and stress_level >= 7:
        state_guidance += (
            "User is highly stressed: recommend shorter focused blocks (20–25 min) "
            "with more frequent breaks to avoid burnout. "
        )
    elif stress_level is not None and stress_level <= 3:
        state_guidance += (
            "User is calm and focused: longer deep-work blocks (45–50 min) are appropriate. "
        )
    if tiredness_level is not None and tiredness_level >= 7:
        state_guidance += (
            "User is tired: break the task into smaller steps, suggest more rest, "
            "and keep individual sessions shorter. "
        )

    prompt = f"""You are an expert productivity coach for students and developers.

Task: "{task_name}"
{user_context}{state_guidance}
Analyse this task and provide a complete structured plan. Be realistic and specific:

- complexity: overall difficulty/scope of the task
- estimated_total_minutes: total wall-clock time including breaks (realistic, not optimistic)
- suggested_sessions: how many Pomodoro-style work rounds to finish the task
- reasoning: 2-3 sentences explaining your estimate and the best approach
- subtasks: 3-7 concrete, ordered, actionable steps — each with a time estimate
- timer_config: work/break durations adapted to the user's state (see guidance above)
- encouragement: one sentence of genuine, specific encouragement for THIS task and user"""

    try:
        client = openai.OpenAI(api_key=api_key)
        response = client.beta.chat.completions.parse(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a structured productivity planning assistant. "
                        "Always respond with valid JSON matching the requested schema exactly. "
                        "Be realistic about time estimates — students often underestimate tasks."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            response_format=TaskAnalysis,
        )
        result = response.choices[0].message.parsed
        if result is None:
            raise HTTPException(
                status_code=502,
                detail="OpenAI returned an empty response. Try again.",
            )
        return result

    except openai.AuthenticationError:
        raise HTTPException(
            status_code=503,
            detail="Invalid OpenAI API key. Check OPENAI_API_KEY in your .env file.",
        )
    except openai.RateLimitError:
        raise HTTPException(
            status_code=429,
            detail="OpenAI rate limit reached. Wait a moment and try again.",
        )
    except openai.OpenAIError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"OpenAI API error: {exc}",
        )
