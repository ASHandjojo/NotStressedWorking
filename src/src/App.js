import './App.css';
import './components/Timer'
import React, { useState, useLayoutEffect, useEffect, useRef, ReactComponent } from 'react'
import ToDoList from './ToDoList.jsx';



const thresholds = {
  stress: 50,
  etc: 0
}
const modes = {
  working: 0,
  break: 1
}
const colors = {
  Red: "#ce5440ff",
  Yellow: "#e4c258ff",
  Green: "#55c04cff",
  White: "#e3e3e2ff",
  Black: "#1c1c1cff"
}
const DEFAULT_MODES = {
  work: { label: "FOCUS", duration: 20 * 60 },
  short: { label: "SHORT BREAK", duration: 5 * 60 },
  long: { label: "LONG BREAK", duration: 15 * 60 },
};

const time = {
  maxTime: 5 * 60
}
function App() {
  const EYE = useRef(null)
  const [mode, setMode] = useState("work");
  const [MODES, setMODES] = useState(DEFAULT_MODES);
  const [timeRemaining, setTimeRemaining] = useState(DEFAULT_MODES.work.duration);
  const [isRunning, setIsRunning] = useState(false);
  const [permissionStatus, setPermissionStatus] = useState(Notification.permission);
  const [hasAskedPermission, setHasAskedPermission] = useState(false);
  const [timeStr, setTimestr] = useState("")
  const modeRef = useRef(mode);
  const [ticks, setTicks] = useState(0)
  useEffect(() => {
    modeRef.current = mode;
  }, [mode]);

  useLayoutEffect(() => {
    // console.log("Effect fired — isRunning:", isRunning, "timeRemaining:", timeRemaining);
    if (!isRunning) return;

    if (timeRemaining <= 0) {
      // Read from ref, not stale closure
      const currentMode = modeRef.current;
      console.log("Perm at fire time:", Notification.permission);
      console.log("timeRemaining:", timeRemaining);
      console.log(Notification.permission)
      if (Notification.permission === "granted") {
        console.log("notification! :D")
        new Notification("Time to switch!", {
          body: `Your ${MODES[currentMode].label} session is over.`,
          image: './PomoLogo.png'
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
      console.log("a")
      updateEye()

    }, 1000);

    return () => clearInterval(interval);
  }, [isRunning, timeRemaining]);

  useEffect(() => {
    if (!isRunning) {
      return
    }
    const a = setInterval(() => {
      setTicks(ticks + 1)
      console.log("aaab")
      updateEye()
    }, 10);
    return () => clearInterval(a);

  }, [ticks])
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
    console.log(isRunning + "->" + !isRunning)
    if (isRunning) setIsRunning(false);
    else startTimer(); // Use startTimer to handle permissions
  };

  const resetTimer = () => {
    console.log('reset!')
    setIsRunning(false);
    setTimeRemaining(MODES[mode].duration);
    updateEye()
  };


  useEffect(() => {
    setTimeout(() => { updateEye() }, 100)
  }, [ticks])

  // Redraw canvas whenever timeRemaining changes (e.g. after config update while timer is stopped)
  useEffect(() => {
    if (!isRunning) {
      setTimeout(() => { updateEye() }, 0)
    }
  }, [timeRemaining, MODES])
  function PomodoroTimer() {
    return (
      <div className="pomodoro-timer">
        <h2>{MODES[mode].label}</h2>


        <div className="controls">
          <button style={{ "backgroundImage": `url('./${(isRunning) ? "pause" : "play"}-${(MODES[mode].label == "FOCUS" ? "red" : (MODES[mode].label == "SHORT BREAK") ? "yellow" : "green")}.png')`, "backgroundSize": "contain", "backgroundRepeat": "no-repeat", "backgroundPosition": "center" }} className='niceButton wide' onClick={toggleTimer}></button>

          <button style={{ "backgroundImage": `url(./skip-${(MODES[mode].label == "FOCUS" ? "red" : (MODES[mode].label == "SHORT BREAK") ? "yellow" : "green")}.png)`, "backgroundSize": "contain", "backgroundRepeat": "no-repeat", "backgroundPosition": "center" }} className='niceButton wide' onClick={resetTimer}></button>

          <hr style={{ "width": "15vw", "padding-left": "vw" }} />
          {Object.keys(MODES).map((m) => (
            <button className='niceButton' style={{ "backgroundColor": (MODES[m].label == "FOCUS" ? colors.Red : (MODES[m].label == "SHORT BREAK") ? colors.Yellow : colors.Green) }} key={m} onClick={() => { setMode(m); setTimeRemaining(MODES[m].duration); startTimer() }} disabled={mode === m}>
              {MODES[m].label}
              <span style={{ display: "block", fontSize: "0.65em", opacity: 0.85 }}>
                {Math.round(MODES[m].duration / 60)} min
              </span>
            </button>
          ))}
        </div>
      </div >
    );
  }

  // Holds the full LLM analysis response once the user submits a project prompt.
  // timer_config goes to PomodoroTimer; subtasks are used inside ToDoList via onAnalysis.
  const [analysis, setAnalysis] = useState(null)

  // When the LLM returns a timer_config, rebuild MODES and reset the current timer.
  useEffect(() => {
    const cfg = analysis?.timer_config;
    if (!cfg) return;
    const newModes = {
      work:  { label: "FOCUS",       duration: cfg.work_minutes * 60 },
      short: { label: "SHORT BREAK", duration: cfg.break_minutes * 60 },
      long:  { label: "LONG BREAK",  duration: cfg.long_break_minutes * 60 },
    };
    setMODES(newModes);
    setIsRunning(false);
    setTimeRemaining(newModes[mode].duration);
  }, [analysis]);

  const updateEye = () => {
    // return
    const canvas = EYE.current
    const cvs = canvas.getContext("2d")

    let eyeBG = new Image(688, 400)
    eyeBG.src = './sclera.png'
    cvs.drawImage(eyeBG, 0, 0, 688, 400)
    cvs.strokeStyle = colors.Red
    cvs.fillStyle = colors.Black
    cvs.lineWidth = "30"
    let arcStart = Math.PI / -2
    console.log(timeRemaining)
    console.log(MODES[mode].duration)

    let arcEnd = (timeRemaining / MODES[mode].duration) * (3 / 2) * Math.PI
    cvs.beginPath()
    cvs.arc(344, 200, 186, arcStart, arcEnd)
    cvs.stroke()
    cvs.beginPath()
    cvs.arc(344, 200, 160, arcStart, arcEnd)
    cvs.stroke()

    cvs.beginPath()
    cvs.arc(344, 200, 150, 0, Math.PI * 2)
    cvs.fill()
    cvs.fillStyle = colors.White
    cvs.font = "70px Overpass Mono"
    let textStr = `${Math.floor(timeRemaining / 60)}:${String(Math.round(timeRemaining) % 60).padStart(2, "0")}`
    cvs.fillText(textStr, 344 - cvs.measureText(textStr).width / 2, 220)

    // let eyeFG = new Image(688, 400)
    // eyeFG.src = './.png'
    // cvs.drawImage(eyeBG, 0, 0, 688, 400)
    // console.log((timeRemaining / MODES[mode].duration))

  }
  return (
    <div className="App" style={{ "fontFamily": "Overpass Mono" }}>
      <link rel="preconnect" href="https://fonts.googleapis.com" />
      <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
      <link href="https://fonts.googleapis.com/css2?family=Overpass+Mono:wght@300..700&display=swap" rel="stylesheet" />
      <title>Pomodoroculus</title>


      <div style={{ justifyContent: "center", display: "flex", align: "center", alignContent: "center" }}><h1 style={{ 'vertical-align': 'middle', 'display': 'inline', "align": "center" }}><img style={{ 'vertical-align': 'top', 'display': 'inline;', "top": "100px", "width": "10vw", "height": "auto" }} src='./PomoLogo.png'></img>&nbsp;Pomodoroculus</h1></div>

      <img src="./sclera.png" style={{ "margin-left": "6vw", "width": "31vw", "height": "18vw", "backgroundColor": "#00000000" }}></img>
      <canvas id="b" width="688" height="400" style={{ "position": "absolute", "margin-left": "0vw", "left": "7vw", "width": "31vw", "height": "18vw", "backgroundColor": "#00000000" }} ref={EYE}></canvas>

      <div id="thing">
        <PomodoroTimer />
        <ToDoList
          onAnalysis={setAnalysis}
          onTimerConfig={(cfg) => setAnalysis(prev => ({ ...(prev || {}), timer_config: cfg }))}
        />
      </div>
      {/* <div className="time-display" style={{ "color": (isRunning ? "var(--white)" : "var(--yellow)") }}>
        {Math.floor(timeRemaining / 60)}:
        {String(timeRemaining % 60).padStart(2, "0")}
      </div> */}

    </div >
  );
}

export default App;
