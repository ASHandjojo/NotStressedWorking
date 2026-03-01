import { useState, useEffect, useRef, useCallback } from "react";

const MODES = {
  work: { label: "FOCUS", duration: 1 * 3 }, // 3 seconds for testing
  short: { label: "SHORT BREAK", duration: 5 * 60 },
  long: { label: "LONG BREAK", duration: 15 * 60 },
};

export default function PomodoroTimer() {
  const [mode, setMode] = useState("work");
  const [timeRemaining, setTimeRemaining] = useState(MODES.work.duration);
  const [isRunning, setIsRunning] = useState(false);
  const [permissionStatus, setPermissionStatus] = useState(Notification.permission);
  const [hasAskedPermission, setHasAskedPermission] = useState(false);

const modeRef = useRef(mode);

useEffect(() => {
  modeRef.current = mode;
}, [mode]);

useEffect(() => {
  console.log("Effect fired — isRunning:", isRunning, "timeRemaining:", timeRemaining);
  if (!isRunning) return;

  if (timeRemaining === 0) {
    // Read from ref, not stale closure
    const currentMode = modeRef.current;
    console.log("Perm at fire time:", Notification.permission);
    console.log("timeRemaining:", timeRemaining);
    console.log(Notification.permission)
    if (Notification.permission === "granted") {
      console.log("notification! :D")
      new Notification("Time to switch!", {
        body: `Your ${MODES[currentMode].label} session is over.`
      });
    }

    const nextMode = currentMode === "work" ? "short" : "work";
    setMode(nextMode);
    setTimeRemaining(MODES[nextMode].duration);
    setIsRunning(true);
    return;
  }

  const interval = setInterval(() => {
    setTimeRemaining((prev) => prev - 1);
  }, 1000);

  return () => clearInterval(interval);
}, [isRunning, timeRemaining]);

  
  // This function is still needed to request permission initially
const requestNotificationPermission = async () => {
  try {
    const permission = await Notification.requestPermission();
    if (permission === 'granted') {
      setHasAskedPermission(true);  // ← replace everything inside with just this
    }
  } catch (error) {
    console.error('Permission error:', error);
  }
};

  const startTimer = async () => {
    // Implicitly ask for permission when they start the first time
    if (!hasAskedPermission && "Notification" in window && Notification.permission !== "granted") {
      await requestNotificationPermission();
      setHasAskedPermission(true);
    }
    setIsRunning(true);
  };

  const toggleTimer = () => {
      if(isRunning) setIsRunning(false);
      else startTimer(); // Use startTimer to handle permissions
  };

  const resetTimer = () => {
    setIsRunning(false);
    setTimeRemaining(MODES[mode].duration);
  };

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