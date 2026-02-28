"""
llm_feedback.py — Stub endpoint for LLM-generated session feedback.

Current state: returns a placeholder response. No LLM is called yet.

── Future Integration Plan ───────────────────────────────────────────────────

Option A — Modal deployment (recommended for hackathon/demo):
  1. Create a Modal function that accepts a session summary dict.
  2. Inside the Modal function, call an open-source LLM (Llama 3, Mistral, etc.)
     via HuggingFace or vLLM.
  3. POST the session summary from this endpoint to the Modal webhook URL.
  4. Add MODAL_WEBHOOK_URL to .env.

Option B — OpenAI API (easiest to wire up):
  1. pip install openai
  2. Add OPENAI_API_KEY to .env.
  3. Use openai.chat.completions.create() with the prompt below.

Prompt template (for either option):
  System: "You are a productivity and wellness coach. Analyse the user's
           biofeedback focus session and give 2–3 actionable tips."
  User:   f"Session duration: {duration}s. Average stress: {avg_stress}.
            Focus score: {focus_score}. Stress trend (first→last): {trend}."

Expected future response shape:
  {
    "feedback": "Your stress peaked around minute 12 ...",
    "tips": ["Try box breathing for 2 minutes", "..."]
  }

TODO:
  - Load session + MetricSamples from DB, build the prompt.
  - Wire up Modal or OpenAI client.
  - Stream the response back if the LLM supports streaming.
  - Add rate limiting per user to control API costs.
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from .auth import get_current_user
from .models import User

router = APIRouter(prefix="/llm-feedback", tags=["llm"])


class FeedbackRequest(BaseModel):
    session_id: int
    # TODO: add optional user_goal field: "deep_work" | "relaxation" | "exercise"


@router.post("")
def get_llm_feedback(
    request: FeedbackRequest,
    current_user: User = Depends(get_current_user),
):
    """
    Return LLM-generated feedback for a completed session.
    Currently a stub — see module docstring for the integration plan.

    TODO: load session from DB, build prompt, call LLM, return real feedback.
    """
    return {
        "session_id": request.session_id,
        "user": current_user.username,
        "message": "LLM feedback not yet implemented",
        "status": "stub",
    }
