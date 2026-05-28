import { useState } from "react";
import reactLogo from "./assets/react.svg";
import { invoke } from "@tauri-apps/api/core";
import Timeline from "./components/Timeline";
import { WorkspaceLayout } from "./workspace/WorkspaceLayout";
import "./App.css";

type View = "workspace" | "home" | "timeline";

function HomeView() {
  const [greetMsg, setGreetMsg] = useState("");
  const [name, setName] = useState("");

  async function greet() {
    // Learn more about Tauri commands at https://tauri.app/develop/calling-rust/
    setGreetMsg(await invoke("greet", { name }));
  }

  return (
    <div className="home">
      <h1>Welcome to Tauri + React</h1>

      <div className="row">
        <a href="https://vite.dev" target="_blank">
          <img src="/vite.svg" className="logo vite" alt="Vite logo" />
        </a>
        <a href="https://tauri.app" target="_blank">
          <img src="/tauri.svg" className="logo tauri" alt="Tauri logo" />
        </a>
        <a href="https://react.dev" target="_blank">
          <img src={reactLogo} className="logo react" alt="React logo" />
        </a>
      </div>
      <p>Click on the Tauri, Vite, and React logos to learn more.</p>

      <form
        className="row"
        onSubmit={(e) => {
          e.preventDefault();
          greet();
        }}
      >
        <input
          id="greet-input"
          onChange={(e) => setName(e.currentTarget.value)}
          placeholder="Enter a name..."
        />
        <button type="submit">Greet</button>
      </form>
      <p>{greetMsg}</p>
    </div>
  );
}

function TimelineView() {
  const [sessionInput, setSessionInput] = useState("");
  const [sessionId, setSessionId] = useState("");

  return (
    <div className="timeline-view">
      <h1>Session Timeline</h1>
      <form
        className="row timeline-view__form"
        onSubmit={(e) => {
          e.preventDefault();
          setSessionId(sessionInput.trim());
        }}
      >
        <input
          value={sessionInput}
          onChange={(e) => setSessionInput(e.currentTarget.value)}
          placeholder="Session ID (UUID)…"
        />
        <button type="submit">Load</button>
      </form>
      <Timeline sessionId={sessionId} />
    </div>
  );
}

function App() {
  const [view, setView] = useState<View>("workspace");

  // The workspace owns the full window (its own dark theme + chrome); the
  // legacy Home/Timeline views keep the sidebar shell.
  if (view === "workspace") {
    return <WorkspaceLayout onNavigateHome={() => setView("home")} />;
  }

  return (
    <div className="app-shell">
      <nav className="sidebar">
        <span className="sidebar__brand">Whetstone</span>
        <button
          type="button"
          className="sidebar__link"
          onClick={() => setView("workspace")}
        >
          Workspace
        </button>
        <button
          type="button"
          className={view === "home" ? "sidebar__link is-active" : "sidebar__link"}
          onClick={() => setView("home")}
        >
          Home
        </button>
        <button
          type="button"
          className={
            view === "timeline" ? "sidebar__link is-active" : "sidebar__link"
          }
          onClick={() => setView("timeline")}
        >
          Timeline
        </button>
      </nav>
      <main className="content">
        {view === "home" ? <HomeView /> : <TimelineView />}
      </main>
    </div>
  );
}

export default App;
