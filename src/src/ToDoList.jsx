import { useState } from "react";
import { analyzeTask, createPlan, tick } from "./api";

export default function ToDoList({ onAnalysis, onTimerConfig }) {
  // ── Planner state ─────────────────────────────────────────────────────────────
  const [timerConfig, setTimerConfig] = useState(null);
  const [prompt, setPrompt] = useState("");
  const [deadline, setDeadline] = useState("");
  const [loading, setLoading] = useState(false);
  const [loadingStep, setLoadingStep] = useState("");
  const [schedule, setSchedule] = useState([]);
  const [planSummary, setPlanSummary] = useState(null);
  const [error, setError] = useState(null);


  // ── Plan handler ────────────────────────────────────────────────────────────
  const handleGenerate = async () => {
    if (!prompt.trim()) return;
    if (!deadline) { setError("Please set a deadline."); return; }

    setLoading(true);
    setError(null);
    setSchedule([]);
    setPlanSummary(null);

    // Convert datetime-local (local time) → UTC ISO string so the server
    // subtracts the right number of minutes regardless of timezone.
    const deadlineUTC = new Date(deadline).toISOString();

    try {
      // Step 1: LLM breaks the project prompt into ordered subtasks
      setLoadingStep("Analyzing project…");
      const analysis = await analyzeTask(prompt);
      onAnalysis?.(analysis);
      const localTimerConfig = analysis.timer_config ?? null;
      setTimerConfig(localTimerConfig);

      // Step 2: Feed subtasks into the adaptive planner
      setLoadingStep("Building your plan…");
      const apiTasks = analysis.subtasks.map((s, i) => ({
        id: `t${i + 1}`,
        description: s.title,
        priority: i + 1,
      }));

      const plan = await createPlan(apiTasks, deadlineUTC, 0.3, 0.3, localTimerConfig);

      if (plan.timer_config) {
        setTimerConfig(plan.timer_config);
        onTimerConfig?.(plan.timer_config);
      }

      setSchedule(plan.schedule.map(s => ({ ...s, done: false })));
      setPlanSummary({
        on_track: plan.on_track,
        remaining_available_minutes: plan.remaining_available_minutes,
        remaining_required_minutes: plan.remaining_required_minutes,
        notes: plan.notes,
      });
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
      setLoadingStep("");
    }
  };

  const handleToggle = async (id) => {
    const item = schedule.find(s => s.id === id);
    if (!item) return;
    const nowDone = !item.done;

    // Optimistic UI update so the checkbox feels instant
    setSchedule(prev => prev.map(s => s.id === id ? { ...s, done: nowDone } : s));

    try {
      const res = await tick(id, item.estimated_minutes, nowDone);

      // Backend now returns ALL tasks (completed + incomplete) in res.schedule.
      // Completed tasks have estimated_minutes replaced with actual time spent.
      // Map completed → done for the frontend.
      setSchedule(res.schedule.map(s => ({ ...s, done: s.completed })));

      // If crunch fired, the backend returns compressed timer durations — update the timer.
      if (res.timer_config) {
        setTimerConfig(res.timer_config);
        onTimerConfig?.(res.timer_config);
      }

      // Update the summary banner
      setPlanSummary(prev => ({
        ...prev,
        on_track: res.on_track,
        remaining_available_minutes: res.remaining_available_minutes,
        remaining_required_minutes: res.remaining_required_minutes,
        // Show adjustment message or replan warning as a note
        notes: [
          ...(res.adjustment_message ? [res.adjustment_message] : []),
          ...(res.replan_needed ? ["⚠️ Plan is structurally overloaded — consider regenerating."] : []),
        ],
      }));
    } catch (err) {
      // Roll back optimistic update on failure
      setSchedule(prev => prev.map(s => s.id === id ? { ...s, done: item.done } : s));
      setError(`Failed to record progress: ${err.message}`);
    }
  };

  // ── Render ──────────────────────────────────────────────────────────────────
  return (
    <div id="toDoList" style={{ position: "relative", top: "-18vw", fontFamily: "Overpass Mono" }}>
      <h2 style={{ marginTop: "1vw" }}>To Do</h2>

      {/* Prompt input */}
      <div style={{ margin: "10px 0" }}>
        <textarea
          value={prompt}
          onChange={e => setPrompt(e.target.value)}
          placeholder="Describe your project or goal… e.g. 'Build a REST API with auth and tests'"
          rows={3}
          style={{ width: "95%", outline: "1px solid black", borderRadius: "1vw", resize: "none", boxSizing: "border-box", resize: "vertical", padding: "8px", fontSize: "0.95rem", fontFamily: "Overpass Mono" }}
        />
      </div>

      {/* Deadline + Generate */}
      <div style={{ display: "flex", flexWrap: "wrap", gap: "8px", alignItems: "center", marginBottom: "12px" }}>
        <label style={{ marginLeft: "2.5%", fontWeight: 600, fontSize: "0.9rem" }}>Deadline:</label>
        <input
          type="datetime-local"
          value={deadline}
          onChange={e => setDeadline(e.target.value)}
          style={{ fontFamily: "Overpass Mono" }}
        />
        <button
          onClick={handleGenerate}
          disabled={loading || !prompt.trim()}
          style={{ fontWeight: 700 }}
        >
          {loading ? loadingStep : "Generate Plan"}
        </button>
      </div>

      {/* Error */}
      {error && (
        <p style={{ color: "red", margin: "0 0 10px", fontSize: "0.85rem" }}>⚠ {error}</p>
      )}

      {/* Plan summary banner */}
      {planSummary && (
        <div style={{
          padding: "10px 12px",
          marginBottom: "12px",
          background: planSummary.on_track ? "#f0faf8" : "#fff4e6",
          borderLeft: `4px solid ${planSummary.on_track ? "#2a9d8f" : "#e07b00"}`,
          borderRadius: "6px",
          fontSize: "0.85rem",
        }}>
          <strong>
            {planSummary.on_track ? "✅ On track" : "⚠️ Tight schedule"}
            {" — "}
            {Math.round(planSummary.remaining_required_minutes)} min needed,{" "}
            {Math.round(planSummary.remaining_available_minutes)} min available
          </strong>
          {planSummary.notes?.length > 0 && (
            <ul style={{ margin: "4px 0 0 0", paddingLeft: "16px" }}>
              {planSummary.notes.map((n, i) => <li key={i}>{n}</li>)}
            </ul>
          )}
        </div>
      )}

      {/* Task list generated from plan */}
      {schedule.length > 0 && (
        <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
          {schedule.map(t => (
            <li key={t.id} style={{
              display: "flex",
              alignItems: "center",
              gap: "10px",
              marginBottom: "8px",
              opacity: t.done ? 0.55 : 1,
            }}>
              <input
                type="checkbox"
                checked={t.done}
                onChange={() => handleToggle(t.id)}
              />
              <span style={{ textDecoration: t.done ? "line-through" : "none", flex: 1 }}>
                {t.description}
              </span>
              <span style={{
                fontSize: "0.78rem",
                color: t.was_compressed ? "#e07b00" : "#2a9d8f",
                fontWeight: 600,
                whiteSpace: "nowrap",
              }}>
                {t.estimated_minutes} min{t.was_compressed ? " ⚡" : ""}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}