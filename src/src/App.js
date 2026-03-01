import './App.css';
import './components/Timer'
import React, { useState, useEffect, useRef } from 'react'
import PomodoroTimer from './pomodoro.jsx';


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
const time = {
  maxTime: 5 * 60
}
function App() {
  const [ws, setWs] = useState(null);
  const [isStressed, setIsStressed] = useState(false)
  const [pts, setPts] = useState([])
  const [mode, setMode] = useState(0)
  const graph = useRef(null)
  const [currTime, setCurrTime] = useState(time.maxTime)
  const EYE = useRef(null)


  useEffect(() => {
    const websocket = new WebSocket('ws://127.0.0.1:8080');

    websocket.onopen = () => {
      console.log('WebSocket is connected');
      // Generate a unique client ID
      const id = Math.floor(Math.random() * 1000);
    };

    websocket.onmessage = (evt) => {
      const message = (evt.data);
      processData(JSON.parse(evt.data))
    };

    websocket.onclose = () => {
      console.log('WebSocket is closed');
    };

    setWs(websocket);

    return () => {
      websocket.close();
    };
  }, []);

  const processData = (data) => {
    setIsStressed(false)
    if (data.stressLevels > thresholds.stress) {
      setIsStressed(true)
    }
    let a = pts
    a.push(data.stressLevels)
    setPts(a)
    updateCvs()

  }

  const updateCvs = () => {
    const canvas = graph.current
    const cvs = canvas.getContext("2d")
    cvs.fillStyle = "#f7d9d9"
    cvs.fillRect(0, 0, 900, 500)

    if (mode == modes.working) {
      cvs.strokeStyle = "black"
      cvs.lineWidth = "3"
    }
    if (mode == modes.break) {
      cvs.strokeStyle = "blue"
      cvs.lineWidth = "3"
    }
    cvs.lineCap = "round"


    let a = pts
    let b = []
    // b => 90 avg vals from pts
    let division = 50
    if (a.length < division) {
      b = a
    } else {

    }
    let dX = 900 / division

    for (let i = 0; i < Math.min(pts.length, division); i++) {
      cvs.beginPath()
      if (pts.length < division) {
        cvs.moveTo(i * dX, pts[i] * 3 + 100)
        cvs.lineTo((i + 1) * dX, pts[i + 1] * 3 + 100)
      } else {
        cvs.moveTo((division - i) * dX, pts[pts.length - i] * 3 + 100)
        cvs.lineTo((division - (i + 1)) * dX, pts[pts.length - i - 1] * 3 + 100)
      }
      cvs.closePath()
      cvs.stroke()
    }
  }

  const updateEye = () => {

  }
  return (
    <div className="App" style={{ "fontFamily": "Overpass Mono", "background-color": `${colors.White}` }}>
      <link rel="preconnect" href="https://fonts.googleapis.com" />
      <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
      <link href="https://fonts.googleapis.com/css2?family=Overpass+Mono:wght@300..700&display=swap" rel="stylesheet" />



      <h1>Not stressed</h1>
      <div id="buttonssns">
        <button className="niceButton" style={{ "backgroundColor": colors.Red }}>Pomodoro</button>
        <button className="niceButton" style={{ "backgroundColor": colors.Yellow }}>Short break</button>
        <button className="niceButton" style={{ "backgroundColor": colors.Green }}>Long break</button>

      </div>

      <p id="vitals">I am stressed: {(isStressed) ? "yes" : "no"}</p>
      <canvas id="a" width="900" height="500" style={{ "width": "45vw", "height": "25vw", "backgroundColor": "#f7d9d9" }} ref={graph}></canvas>
      <canvas id="b" width="688" height="400" style={{ "width": "45vw", "height": "25vw", "backgroundColor": "#f7d9d9" }} ref={EYE}></canvas>
      <div style={{ marginTop: "20px", border: "1px solid #ccc", padding: "20px", borderRadius: "10px" }}>
        <PomodoroTimer />
      </div>

    </div >
  );
}

export default App;
