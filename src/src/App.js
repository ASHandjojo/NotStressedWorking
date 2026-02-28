import './App.css';
import './components/Timer'
import React, { useState, useEffect, useRef } from 'react'

const thresholds = {
  stress: 50,
  etc: 0
}
function App() {
  const [ws, setWs] = useState(null);
  const [isStressed, setIsStressed] = useState(false)
  const [pts, setPts] = useState([])
  const graph = useRef(null)

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
    let dX = 900 / pts.length
    cvs.fillRect(0, 0, 900, 500)
    cvs.fillStyle = "black"
    let a = pts
    let b = []
    // b => 90 avg vals from pts

    if (a.length < 90) {
      b = a
    } else {

    }

    for (let i = 0; i < pts.length - 1; i++) {
      cvs.beginPath()
      cvs.moveTo(i * dX, pts[i] * 3 + 100)
      cvs.lineTo((i + 1) * dX, pts[i + 1] * 3 + 100)
      cvs.closePath()
      cvs.stroke()
    }
  }

  return (

    <div className="App" style={{ "fontFamily": "Overpass Mono" }}>
      <link rel="preconnect" href="https://fonts.googleapis.com" />
      <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
      <link href="https://fonts.googleapis.com/css2?family=Overpass+Mono:wght@300..700&display=swap" rel="stylesheet" />

      <h1>Not stressed</h1>
      <p id="vitals">I am stressed: {(isStressed) ? "yes" : "no"}</p>
      <canvas width="900" height="500" style={{ "width": "45vw", "height": "25vw", "backgroundColor": "#f7d9d9" }} ref={graph}></canvas>

    </div >
  );
}

export default App;
