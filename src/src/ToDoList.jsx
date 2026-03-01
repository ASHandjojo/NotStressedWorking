import { useState } from "react";

export default function ToDoList() {
  const [tasks, setTasks] = useState([]);
  const [input, setInput] = useState("");

  const addTask = () => {
    if (!input.trim()) return;
    setTasks([...tasks, { id: Date.now(), text: input, done: false }]);
    setInput("");
  };

  const toggleTask = (id) => {
    setTasks(tasks.map(t => t.id === id ? { ...t, done: !t.done } : t));
  };

  const deleteTask = (id) => {
    setTasks(tasks.filter(t => t.id !== id));
  };

  return (
    <div id="toDoList">
      <h2>To Do</h2>
      <div>
        <input
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => e.key === "Enter" && addTask()}
          placeholder="Add a task..."
        />
        <button onClick={addTask}>Add</button>
      </div>
      <ul>
        {tasks.map(t => (
          <li key={t.id} style={{ display: "flex", alignItems: "center", gap: "10px", marginBottom: "6px" }}>
            <input
              type="checkbox"
              checked={t.done}
              onChange={() => toggleTask(t.id)}
            />
            <span style={{ textDecoration: t.done ? "line-through" : "none", flex: 1 }}>
              {t.text}
            </span>
            <button onClick={() => deleteTask(t.id)}>✕</button>
          </li>
        ))}
      </ul>
    </div>
  );
}