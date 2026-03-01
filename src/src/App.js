import './App.css';
import './components/Timer'
import React, { useState, useEffect, useRef } from 'react'
import PomodoroTimer from './pomodoro.jsx';
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
const time = {
  maxTime: 5 * 60
}
function App() {
  const EYE = useRef(null)

  const updateEye = () => {

  }
  return (
    <div className="App" style={{ "fontFamily": "Overpass Mono", "background-color": `${colors.White}` }}>
      <link rel="preconnect" href="https://fonts.googleapis.com" />
      <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
      <link href="https://fonts.googleapis.com/css2?family=Overpass+Mono:wght@300..700&display=swap" rel="stylesheet" />
      <title>Nostresso</title>


      <h1>Nostresso</h1>
      {/* <div id="buttonssns">
        <button className="niceButton" style={{ "backgroundColor": colors.Red }}>Pomodoro</button>
        <button className="niceButton" style={{ "backgroundColor": colors.Yellow }}>Short break</button>
        <button className="niceButton" style={{ "backgroundColor": colors.Green }}>Long break</button>
      </div> */}

      {/* <canvas id="b" width="688" height="400" style={{ "width": "45vw", "height": "25vw", "backgroundColor": "#f7d9d9" }} ref={EYE}></canvas> */}
      <div id="thing">
        <PomodoroTimer />
        <ToDoList />
      </div>


    </div >
  );
}

export default App;
