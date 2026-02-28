import { useState, useEffect, useRef, useCallback } from "react";

const MODES = {
  work: { label: "FOCUS", duration: 25 * 60 },
  short: { label: "SHORT BREAK", duration: 5 * 60 },
  long: { label: "LONG BREAK", duration: 15 * 60 },
};

export default function PomodoroTimer() {
  const [mode, setMode] = useState("work");
  const [timeRemaining, setTimeRemaining] = useState(MODES.work.duration);
  const [isRunning, setIsRunning] = useState(false);
  //reset timer when mode changesg
  useEffect(() => {
    setTimeRemaining(MODES[mode].duration);
    setIsRunning(false);
  }, [mode]);

   useEffect(() => {
    let interval = null;

    if (isRunning && timeRemaining > 0) {
      interval = setInterval(() => {
        setTimeRemaining((prev) => prev - 1);
      }, 1000);
    } else if (timeRemaining === 0) {
      clearInterval(interval);

      const nextMode = mode === "work" ? "short" : "work";
      setMode(nextMode);
      setTimeRemaining(MODES[nextMode].duration);

      setIsRunning(true);
    }

    return () => clearInterval(interval);
  }, [isRunning, timeRemaining, mode]);

  const toggleTimer = () => setIsRunning(!isRunning);  //reset timer to current mode duration
  const resetTimer = () => {
    setIsRunning(false);
    setTimeRemaining(MODES[mode].duration);
  };
  //switch mode and reset timer
  return (
    <div className="pomodoro-timer">
      <h2>{MODES[mode].label}</h2>
      <div className="time-display">
        {Math.floor(timeRemaining / 60)}:
        {String(timeRemaining % 60).padStart(2, "0")}
      </div>
      <div className="controls">
        <button onClick={toggleTimer}>{isRunning ? "Pause" : "Start"}</button>
        <button onClick={resetTimer}>Reset</button>
        <hr />
        {Object.keys(MODES).map((m) => (
          <button key={m} onClick={() => setMode(m)} disabled={mode === m}>
            {MODES[m].label}
          </button>
        ))}
      </div>
    </div>
  );
}