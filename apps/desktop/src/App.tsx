import { useState } from "react";
import Timeline from "./components/Timeline";
import { WorkspaceLayout } from "./workspace/WorkspaceLayout";
import { PracticeView } from "./practice/PracticeView";
import "./App.css";

type View = "workspace" | "home" | "timeline" | "practice";

function HomeView() {
  return (
    <div className="home">
      <h1>Whetstone</h1>
      <p>
        A local-first problem-solving environment for CS students — your code,
        your reasoning, and an on-device AI tutor, all on your own machine.
      </p>
      <p>
        The <strong>Workspace</strong> is where you do the work: write and run
        cells, track spec requirements, ask the co-pilot, and replay your
        session timeline. <strong>Practice</strong> holds the beginner coding
        course and a DSA problem bank — your local model can even write new
        problems shaped like the ones you struggle with. The{" "}
        <strong>Timeline</strong> tab loads any session by id. Use the sidebar
        to switch between them.
      </p>
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
  // When Practice starts a session, the workspace opens that exact session
  // instead of its usual most-recently-modified pick.
  const [workspaceSessionId, setWorkspaceSessionId] = useState<string | null>(null);

  const openSessionInWorkspace = (sessionId: string) => {
    setWorkspaceSessionId(sessionId);
    setView("workspace");
  };

  // The workspace owns the full window (its own dark theme + chrome); the
  // legacy Home/Timeline/Practice views keep the sidebar shell. Keying by
  // session forces a clean re-bootstrap when Practice hands over a session.
  if (view === "workspace") {
    return (
      <WorkspaceLayout
        key={workspaceSessionId ?? "latest"}
        sessionId={workspaceSessionId}
        onNavigateHome={() => setView("home")}
      />
    );
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
          className={
            view === "practice" ? "sidebar__link is-active" : "sidebar__link"
          }
          onClick={() => setView("practice")}
        >
          Practice
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
        {view === "home" ? (
          <HomeView />
        ) : view === "practice" ? (
          <PracticeView onOpenSession={openSessionInWorkspace} />
        ) : (
          <TimelineView />
        )}
      </main>
    </div>
  );
}

export default App;
