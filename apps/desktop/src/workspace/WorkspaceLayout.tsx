import { useEffect, useRef, useState } from "react";
import {
  API_BASE,
  createCell,
  createSession,
  listRequirements,
  listSessions,
  runCell,
  updateCell,
  updateRequirement,
  askStream,
  type ApiError,
} from "../api";
import type { AiMode, AskRequest, RequirementItemRead, RequirementStatus, SessionRead } from "../types";
import { Header } from "./Header";
import { RequirementsPane } from "./RequirementsPane";
import { NotebookPane } from "./NotebookPane";
import { CoPilotPane, type ChatMessage } from "./CoPilotPane";
import { Footer } from "./Footer";
import { TimelineDrawer } from "./TimelineDrawer";

const LANGUAGE = "cpp";
const CELL_LABEL = "Cell 01";
const FILE_NAME = "scratchpad.cpp";

// Seed cell shown on every fresh notebook (decision: start from the seed, do not
// imply prior cells are restored — there is no GET /sessions/{id}/cells route).
const SEED_CODE = `// Compiled via system clang++ toolchain
#include <iostream>
#include <unistd.h>

int main() {
    std::cout << "[Psirver] Init loopback worker PID: " << getpid() << std::endl;
    return 0;
}`;

function apiHost(): string {
  try {
    return new URL(API_BASE).host;
  } catch {
    return API_BASE;
  }
}

function uid(): string {
  return crypto.randomUUID();
}

type Props = {
  onNavigateHome: () => void;
};

export function WorkspaceLayout({ onNavigateHome }: Props) {
  const [session, setSession] = useState<SessionRead | null>(null);
  const [online, setOnline] = useState(true);
  const [bootstrapped, setBootstrapped] = useState(false);

  const [requirements, setRequirements] = useState<RequirementItemRead[]>([]);
  const [reqLoading, setReqLoading] = useState(false);

  const [mode, setMode] = useState<AiMode>("direct");
  const [recording, setRecording] = useState(false);
  const [timelineOpen, setTimelineOpen] = useState(false);
  const [lastActivity, setLastActivity] = useState<string | null>(null);

  // Notebook cell (single cell for v1).
  const [content, setContent] = useState(SEED_CODE);
  const [serverCellId, setServerCellId] = useState<string | null>(null);
  const [lastSyncedContent, setLastSyncedContent] = useState<string | null>(null);
  const [running, setRunning] = useState(false);
  const [output, setOutput] = useState<string | null>(null);
  const [cellStatus, setCellStatus] = useState("");
  const [runNote, setRunNote] = useState<string | null>(null);

  // Co-pilot.
  const [thread, setThread] = useState<ChatMessage[]>([]);
  const [aiBusy, setAiBusy] = useState(false);

  const runAbortRef = useRef<AbortController | null>(null);
  const askAbortRef = useRef<AbortController | null>(null);

  // Bootstrap: reuse the most recently modified session, else create one. If the
  // backend is unreachable, fall back to a local-only shell (offline-first).
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const sessions = await listSessions();
        const picked = sessions[0] ?? (await createSession({ title: "Whetstone workspace" }));
        if (cancelled) return;
        setSession(picked);
        setOnline(true);
        if (picked.spec_id) {
          setReqLoading(true);
          try {
            const reqs = await listRequirements(picked.spec_id);
            if (!cancelled) setRequirements(reqs);
          } catch {
            // Leave the checklist empty; the pane explains the empty state.
          } finally {
            if (!cancelled) setReqLoading(false);
          }
        }
      } catch {
        if (!cancelled) {
          setOnline(false);
          setSession(null);
        }
      } finally {
        if (!cancelled) setBootstrapped(true);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const changeRequirementStatus = async (id: string, status: RequirementStatus) => {
    const prev = requirements;
    setRequirements((rs) => rs.map((r) => (r.id === id ? { ...r, status } : r)));
    setLastActivity(`Requirement → ${status}`);
    try {
      await updateRequirement(id, { status });
    } catch {
      setRequirements(prev); // revert on failure
      setLastActivity("Requirement update failed");
    }
  };

  const runCellNow = async () => {
    if (running) return;
    if (!online || !session) {
      setOutput("Backend is offline — start it to run cells on the local engine.");
      setCellStatus("error");
      setRunNote(null);
      setLastActivity("Run blocked — backend offline");
      return;
    }
    setRunNote(null);
    setRunning(true);
    setLastActivity("Running cell on the local engine…");
    const controller = new AbortController();
    runAbortRef.current = controller;
    try {
      let cellId = serverCellId;
      if (!cellId) {
        const created = await createCell({
          session_id: session.id,
          cell_type: "code",
          language: LANGUAGE,
          content,
        });
        cellId = created.id;
        setServerCellId(cellId);
        setLastSyncedContent(content);
      } else if (content !== lastSyncedContent) {
        await updateCell(cellId, { content });
        setLastSyncedContent(content);
      }
      const result = await runCell(cellId, controller.signal);
      setOutput(result.last_output ?? "");
      setCellStatus(result.status);
      setLastActivity(`Cell run · ${result.status}`);
    } catch (err) {
      if ((err as Error)?.name === "AbortError") {
        // Cancellation is surfaced by cancelRun; nothing to do here.
      } else {
        const e = err as ApiError;
        setOutput(e?.message ?? String(err));
        setCellStatus("error");
        setLastActivity("Cell run failed");
      }
    } finally {
      setRunning(false);
      runAbortRef.current = null;
    }
  };

  const cancelRun = () => {
    runAbortRef.current?.abort();
    runAbortRef.current = null;
    setRunning(false);
    setRunNote("Request cancelled; the server job continues to completion.");
    setLastActivity("Run cancelled (server job continues)");
  };

  const clearCell = () => {
    setOutput(null);
    setCellStatus("");
    setRunNote(null);
  };

  const changeMode = (m: AiMode) => {
    setMode(m);
    setLastActivity(`Tutor mode → ${m}`);
  };

  const askTutor = (question: string) => {
    if (mode !== "direct" || aiBusy) return;
    const tutorId = uid();
    setThread((t) => [
      ...t,
      { id: uid(), role: "student", text: question },
      { id: tutorId, role: "tutor", text: "", streaming: true },
    ]);
    setAiBusy(true);
    setLastActivity("Asked the co-pilot…");

    const settle = (patch: Partial<ChatMessage>) =>
      setThread((t) => t.map((m) => (m.id === tutorId ? { ...m, ...patch } : m)));

    if (!online || !session) {
      settle({ text: "Backend is offline — start it to ask the local co-pilot.", streaming: false, errored: true });
      setAiBusy(false);
      return;
    }

    const controller = new AbortController();
    askAbortRef.current = controller;
    const body: AskRequest = {
      session_id: session.id,
      cell_id: serverCellId,
      question,
      mode: "direct",
    };

    askStream(
      body,
      {
        onDelta: (delta) => setThread((t) => t.map((m) => (m.id === tutorId ? { ...m, text: m.text + delta } : m))),
        onError: (msg) => {
          settle({ text: msg, streaming: false, errored: true });
          setAiBusy(false);
        },
        onDone: () => {
          settle({ streaming: false });
          setAiBusy(false);
          setLastActivity("Co-pilot replied");
        },
      },
      controller.signal,
    ).catch((err) => {
      const e = err as ApiError;
      const msg =
        e?.status === 501
          ? "Socratic mode is not implemented yet."
          : (e?.message ?? "The local co-pilot is unavailable.");
      settle({ text: msg, streaming: false, errored: true });
      setAiBusy(false);
    });
  };

  return (
    <div className="workspace-root">
      <div className="h-full w-full flex flex-col relative">
        <Header
          recording={recording}
          onToggleRecording={() => setRecording((r) => !r)}
          onNavigateHome={onNavigateHome}
          online={online}
          breadcrumb={{ project: session?.title ?? "local session", file: FILE_NAME }}
        />

        {recording && (
          <div className="shrink-0 h-6 bg-red-950/30 border-b border-red-900/50 flex items-center justify-center gap-2 text-[10.5px] font-medium text-red-300">
            <span className="w-1.5 h-1.5 rounded-full bg-red-500 pulse-dot" aria-hidden />
            Recording placeholder — on-device voice capture isn't wired yet (POST /ai/transcribe is a stub).
          </div>
        )}

        <div className="flex-1 min-h-0 flex">
          <RequirementsPane
            requirements={requirements}
            hasSpec={Boolean(session?.spec_id)}
            loading={reqLoading || !bootstrapped}
            online={online}
            onStatusChange={changeRequirementStatus}
          />
          <NotebookPane
            cellLabel={CELL_LABEL}
            language={LANGUAGE}
            content={content}
            onChange={setContent}
            running={running}
            output={output}
            status={cellStatus}
            note={runNote}
            onRun={runCellNow}
            onCancel={cancelRun}
            onClear={clearCell}
          />
          <CoPilotPane mode={mode} onModeChange={changeMode} thread={thread} busy={aiBusy} onSend={askTutor} />
        </div>

        <Footer
          online={online}
          lastActivity={lastActivity}
          apiHost={apiHost()}
          onOpenTimeline={() => setTimelineOpen(true)}
        />

        <TimelineDrawer open={timelineOpen} onClose={() => setTimelineOpen(false)} sessionId={session?.id ?? ""} />
      </div>
    </div>
  );
}

export default WorkspaceLayout;
