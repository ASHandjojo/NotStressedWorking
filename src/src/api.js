/**
 * api.js — Backend client for NotStressed FastAPI server.
 *
 * All functions return parsed JSON or throw an Error with the server's
 * detail message so callers can show it in the UI.
 *
 * Usage:
 *   import { createPlan, tick, analyzTask } from './api';
 *
 * Auth:
 *   Call login() first to get a token, then pass it to any function
 *   that requires it (tasks, sessions). Scheduler endpoints (plan/tick/replan)
 *   don't require a token.
 */

const BASE = "http://localhost:8000";

// Token comes from REACT_APP_API_TOKEN in src/.env — injected at build time by CRA.
// All auth-gated calls use this automatically; nothing is stored in component state.
const API_TOKEN = process.env.REACT_APP_API_TOKEN ?? "";

// ── Helpers ───────────────────────────────────────────────────────────────────

async function request(path, options = {}) {
  const res = await fetch(`${BASE}${path}`, options);
  const data = await res.json();
  if (!res.ok) {
    throw new Error(data?.detail ?? `Request failed: ${res.status}`);
  }
  return data;
}

function authHeaders(token) {
  return {
    "Content-Type": "application/json",
    Authorization: `Bearer ${token}`,
  };
}

function jsonHeaders() {
  return { "Content-Type": "application/json" };
}

// ── Auth ──────────────────────────────────────────────────────────────────────

/** Register a new user. Returns { message, user_id }. */
export async function register(username, password) {
  const body = new URLSearchParams({ username, password });
  return request("/auth/register", {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body,
  });
}

/**
 * Login and get a JWT token.
 * Returns { access_token, token_type }.
 * Store access_token in state/localStorage and pass to other calls.
 */
export async function login(username, password) {
  const body = new URLSearchParams({ username, password });
  return request("/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body,
  });
}

// ── Scheduler (no auth required) ─────────────────────────────────────────────

/**
 * Create a deadline-aware adaptive plan.
 *
 * @param {Array}  tasks        - [{ id, description, priority }]
 * @param {string} deadline     - ISO 8601, e.g. "2026-03-02T23:59:00"
 * @param {number} tiredness    - 0.0–1.0
 * @param {number} stress       - 0.0–1.0
 * @returns PlanResponse
 */
export async function createPlan(tasks, deadline, tiredness = 0.3, stress = 0.3) {
  return request("/v1/plan", {
    method: "POST",
    headers: jsonHeaders(),
    body: JSON.stringify({
      tasks,
      deadline,
      current_time: new Date().toISOString(),
      tiredness,
      stress,
    }),
  });
}

/**
 * Record progress on a task and get an updated schedule.
 * replan_needed=true in the response means you should call replan().
 *
 * @param {string}  taskId        - id of the task being reported
 * @param {number}  minutesSpent  - how long was spent (analytics only)
 * @param {boolean} completed     - whether the task is done
 * @returns TickResponse
 */
export async function tick(taskId, minutesSpent, completed) {
  return request("/v1/tick", {
    method: "POST",
    headers: jsonHeaders(),
    body: JSON.stringify({
      task_id: taskId,
      minutes_spent: minutesSpent,
      completed,
      current_time: new Date().toISOString(),
    }),
  });
}

/**
 * Re-run LLM estimation for incomplete tasks.
 * Call when tick() returns replan_needed=true.
 *
 * @param {number} tiredness  - updated tiredness level
 * @param {number} stress     - updated stress level
 * @returns PlanResponse (with task_changes showing skipped/reformulated tasks)
 */
export async function replan(tiredness, stress) {
  return request("/v1/replan", {
    method: "POST",
    headers: jsonHeaders(),
    body: JSON.stringify({
      current_time: new Date().toISOString(),
      tiredness,
      stress,
    }),
  });
}

/** Dump raw in-memory plan state. Useful for debugging. */
export async function debugState() {
  return request("/v1/debug/state");
}

// ── Task Analysis (auth required) ────────────────────────────────────────────

/**
 * Analyze a project prompt with LLM (does NOT save to DB).
 * Returns complexity, subtasks[], timer config, encouragement.
 *
 * @param {string} taskName
 * @param {string} token
 * @param {number} [stressLevel]    - 1–10, optional
 * @param {number} [tirednessLevel] - 1–10, optional
 */
export async function analyzeTask(taskName, stressLevel = null, tirednessLevel = null) {
  return request("/tasks/analyze", {
    method: "POST",
    headers: authHeaders(API_TOKEN),
    body: JSON.stringify({
      task_name: taskName,
      stress_level: stressLevel,
      tiredness_level: tirednessLevel,
    }),
  });
}

/**
 * Analyze + save a task to DB.
 * Returns the saved TaskRecord.
 */
export async function saveTask(taskName, stressLevel, tirednessLevel) {
  return request("/tasks/", {
    method: "POST",
    headers: authHeaders(API_TOKEN),
    body: JSON.stringify({
      task_name: taskName,
      stress_level: stressLevel,
      tiredness_level: tirednessLevel,
    }),
  });
}

/** List all saved tasks. */
export async function listTasks() {
  return request("/tasks/", { headers: authHeaders(API_TOKEN) });
}

/** Delete a saved task by id. */
export async function deleteTask(taskId) {
  return request(`/tasks/${taskId}`, {
    method: "DELETE",
    headers: authHeaders(API_TOKEN),
  });
}

// ── Sessions (auth required) ──────────────────────────────────────────────────

/** Start a Pomodoro work session for a task. */
export async function startSession(taskRecordId, subtaskIndex = 0) {
  return request("/sessions/start", {
    method: "POST",
    headers: authHeaders(API_TOKEN),
    body: JSON.stringify({ task_record_id: taskRecordId, subtask_index: subtaskIndex }),
  });
}

/** Mark a session complete. */
export async function completeSession(sessionId, durationMinutes) {
  return request(`/sessions/${sessionId}/complete`, {
    method: "POST",
    headers: authHeaders(API_TOKEN),
    body: JSON.stringify({ duration_minutes: durationMinutes }),
  });
}

/** Abandon a session. */
export async function abandonSession(sessionId) {
  return request(`/sessions/${sessionId}/abandon`, {
    method: "POST",
    headers: authHeaders(API_TOKEN),
  });
}

/** List all sessions. */
export async function listSessions() {
  return request("/sessions/", { headers: authHeaders(API_TOKEN) });
}

// ── Health ────────────────────────────────────────────────────────────────────

/** Check if the server is up and OpenAI is configured. */
export async function health() {
  return request("/health");
}
