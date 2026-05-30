import { useEffect, useRef, useState } from "react";
import {
  API_BASE,
  createCell,
  createSession,
  listRequirements,
  listSessionCells,
  listSessions,
  runCell,
  updateCell,
  updateRequirement,
  askStream,
  transcribeAudio,
  type ApiError,
  type CellRead,
} from "../api";
import type { AiMode, AskRequest, RequirementItemRead, RequirementStatus, SessionRead } from "../types";
import { Header, type VoiceState } from "./Header";
import { RequirementsPane } from "./RequirementsPane";
import { NotebookPane, type NotebookCell } from "./NotebookPane";
import { CoPilotPane, type ChatMessage } from "./CoPilotPane";
import { Footer } from "./Footer";
import { TimelineDrawer } from "./TimelineDrawer";

const FILE_NAME = "scratchpad.cpp";

// Seed cell created for a brand-new (empty) session so the notebook opens with
// a runnable starter rather than a blank canvas. It is persisted server-side,
// so it restores on reload like any other cell.
const SEED_CODE = `// Compiled via system clang++ toolchain
#include <iostream>
#include <unistd.h>

int main() {
    std::cout << "[Psirver] Init loopback worker PID: " << getpid() << std::endl;
    return 0;
}`;

// Starter source for cells the user adds, so a fresh cell runs to real output.
const STARTERS: Record<string, string> = {
  python: 'print("hello from python")',
  cpp: `#include <iostream>

int main() {
    std::cout << "hello from c++" << std::endl;
    return 0;
}`,
};

function starterFor(language: string): string {
  return STARTERS[language] ?? "";
}

// Build the UI view-model from a server cell. A never-run cell has status
// "idle" server-side; map that to "" so the output pane shows the empty state.
function toView(cell: CellRead): NotebookCell {
  return {
    id: cell.id,
    language: cell.language ?? "python",
    content: cell.content,
    output: cell.last_output,
    status: cell.status === "idle" ? "" : cell.status,
    running: false,
    note: null,
  };
}

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
  const [voiceState, setVoiceState] = useState<VoiceState>("idle");
  const [timelineOpen, setTimelineOpen] = useState(false);
  const [lastActivity, setLastActivity] = useState<string | null>(null);

  // Voice dictation: capture audio with MediaRecorder, then POST it to
  // /ai/transcribe and drop the transcript into the co-pilot prompt.
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const mediaStreamRef = useRef<MediaStream | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);

  // Notebook cells, in display order.
  const [cells, setCells] = useState<NotebookCell[]>([]);
  const [adding, setAdding] = useState(false);
  // The cell the co-pilot reasons about (last focused / added). Sent as
  // AskRequest.cell_id so the tutor has the relevant cell in context.
  const [activeCellId, setActiveCellId] = useState<string | null>(null);
  // Per-cell content last synced to the server, so we only PUT on real edits.
  const lastSyncedRef = useRef<Map<string, string>>(new Map());
  // Per-cell in-flight run controllers, so each cell cancels independently.
  const runAbortRef = useRef<Map<string, AbortController>>(new Map());

  // Co-pilot.
  const [thread, setThread] = useState<ChatMessage[]>([]);
  const [aiBusy, setAiBusy] = useState(false);
  // Prompt draft is owned here (not in CoPilotPane) so dictation can inject into it.
  const [draft, setDraft] = useState("");

  const askAbortRef = useRef<AbortController | null>(null);

  const patchCell = (cellId: string, patch: Partial<NotebookCell>) =>
    setCells((cs) => cs.map((c) => (c.id === cellId ? { ...c, ...patch } : c)));

  // Bootstrap: reuse the most recently modified session (else create one), then
  // restore its cells and their last outputs. If the backend is unreachable,
  // fall back to a local-only shell with one starter cell (offline-first).
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const sessions = await listSessions();
        const picked = sessions[0] ?? (await createSession({ title: "Whetstone workspace" }));
        if (cancelled) return;
        setSession(picked);
        setOnline(true);

        const existing = await listSessionCells(picked.id);
        if (cancelled) return;
        let views: NotebookCell[];
        if (existing.length > 0) {
          existing.forEach((c) => lastSyncedRef.current.set(c.id, c.content));
          views = existing.map(toView);
        } else {
          const seed = await createCell({
            session_id: picked.id,
            cell_type: "code",
            language: "cpp",
            content: SEED_CODE,
          });
          if (cancelled) return;
          lastSyncedRef.current.set(seed.id, seed.content);
          views = [toView(seed)];
        }
        setCells(views);
        setActiveCellId(views[0]?.id ?? null);

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
          // Local-only starter cell so the notebook isn't blank offline. Its id
          // never reaches the server: runs and Add are gated on `online`.
          const localId = uid();
          setCells([
            {
              id: localId,
              language: "cpp",
              content: SEED_CODE,
              output: null,
              status: "",
              running: false,
              note: null,
            },
          ]);
          setActiveCellId(localId);
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

  const changeCellContent = (cellId: string, content: string) => patchCell(cellId, { content });

  const focusCell = (cellId: string) => setActiveCellId(cellId);

  const addCell = async (language: string) => {
    if (adding) return;
    if (!online || !session) return; // Add is gated on a live backend.
    setAdding(true);
    setLastActivity(`Adding ${language === "cpp" ? "C++" : "Python"} cell…`);
    try {
      const created = await createCell({
        session_id: session.id,
        cell_type: "code",
        language,
        content: starterFor(language),
      });
      lastSyncedRef.current.set(created.id, created.content);
      setCells((cs) => [...cs, toView(created)]);
      setActiveCellId(created.id);
      setLastActivity(`Added ${language === "cpp" ? "C++" : "Python"} cell`);
    } catch (err) {
      const e = err as ApiError;
      setLastActivity(`Add cell failed: ${e?.message ?? String(err)}`);
    } finally {
      setAdding(false);
    }
  };

  const runCellNow = async (cellId: string) => {
    const cell = cells.find((c) => c.id === cellId);
    if (!cell || cell.running) return;
    if (!online || !session) {
      patchCell(cellId, {
        output: "Backend is offline — start it to run cells on the local engine.",
        status: "error",
        note: null,
      });
      setLastActivity("Run blocked — backend offline");
      return;
    }
    setActiveCellId(cellId);
    patchCell(cellId, { running: true, note: null });
    setLastActivity("Running cell on the local engine…");
    const controller = new AbortController();
    runAbortRef.current.set(cellId, controller);
    try {
      if (cell.content !== lastSyncedRef.current.get(cellId)) {
        await updateCell(cellId, { content: cell.content });
        lastSyncedRef.current.set(cellId, cell.content);
      }
      const result = await runCell(cellId, controller.signal);
      patchCell(cellId, { output: result.last_output ?? "", status: result.status });
      setLastActivity(`Cell run · ${result.status}`);
    } catch (err) {
      if ((err as Error)?.name === "AbortError") {
        // Cancellation is surfaced by cancelRun; nothing to do here.
      } else {
        const e = err as ApiError;
        patchCell(cellId, { output: e?.message ?? String(err), status: "error" });
        setLastActivity("Cell run failed");
      }
    } finally {
      runAbortRef.current.delete(cellId);
      patchCell(cellId, { running: false });
    }
  };

  const cancelRun = (cellId: string) => {
    runAbortRef.current.get(cellId)?.abort();
    runAbortRef.current.delete(cellId);
    patchCell(cellId, {
      running: false,
      note: "Request cancelled; the server job continues to completion.",
    });
    setLastActivity("Run cancelled (server job continues)");
  };

  const clearCell = (cellId: string) => patchCell(cellId, { output: null, status: "", note: null });

  const changeMode = (m: AiMode) => {
    setMode(m);
    setLastActivity(`Tutor mode → ${m}`);
  };

  const askTutor = (question: string) => {
    if (aiBusy) return;
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
      cell_id: activeCellId,
      question,
      mode,
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
      settle({
        text: e?.message ?? "The local co-pilot is unavailable.",
        streaming: false,
        errored: true,
      });
      setAiBusy(false);
    });
  };

  // --- Voice dictation -----------------------------------------------------

  const startRecording = async () => {
    if (!online || !session) {
      setLastActivity("Voice blocked — backend offline");
      return;
    }
    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch {
      setLastActivity("Microphone unavailable — check permissions");
      return;
    }
    mediaStreamRef.current = stream;
    audioChunksRef.current = [];
    const recorder = new MediaRecorder(stream);
    recorder.ondataavailable = (e) => {
      if (e.data.size > 0) audioChunksRef.current.push(e.data);
    };
    recorder.onstop = () => {
      void finishRecording(recorder.mimeType);
    };
    mediaRecorderRef.current = recorder;
    recorder.start();
    setVoiceState("recording");
    setLastActivity("Recording — dictating to the co-pilot…");
  };

  const stopRecording = () => {
    const recorder = mediaRecorderRef.current;
    if (recorder && recorder.state !== "inactive") recorder.stop();
  };

  // Runs once the recorder flushes its last chunk: release the mic, send the
  // audio to whisper-server, and append the transcript to the prompt draft.
  const finishRecording = async (mimeType: string) => {
    mediaStreamRef.current?.getTracks().forEach((t) => t.stop());
    mediaStreamRef.current = null;
    mediaRecorderRef.current = null;
    const chunks = audioChunksRef.current;
    audioChunksRef.current = [];
    if (chunks.length === 0) {
      setVoiceState("idle");
      return;
    }
    setVoiceState("transcribing");
    setLastActivity("Transcribing on the local engine…");
    try {
      const blob = new Blob(chunks, { type: mimeType || "audio/webm" });
      const { transcript } = await transcribeAudio(blob);
      const clean = transcript.trim();
      if (clean) {
        setDraft((d) => (d ? `${d} ${clean}` : clean));
        setLastActivity("Voice transcript added to the co-pilot");
      } else {
        setLastActivity("No speech detected");
      }
    } catch (err) {
      const e = err as ApiError;
      setLastActivity(`Transcription failed: ${e?.message ?? String(err)}`);
    } finally {
      setVoiceState("idle");
    }
  };

  const toggleVoice = () => {
    if (voiceState === "recording") stopRecording();
    else if (voiceState === "idle") void startRecording();
    // Ignore toggles while transcribing — the button is disabled then anyway.
  };

  // Release the microphone if the workspace unmounts mid-recording. Drop the
  // onstop handler first so it doesn't fire transcription into a dead component.
  useEffect(() => {
    return () => {
      const recorder = mediaRecorderRef.current;
      if (recorder) {
        recorder.onstop = null;
        if (recorder.state !== "inactive") recorder.stop();
      }
      mediaStreamRef.current?.getTracks().forEach((t) => t.stop());
    };
  }, []);

  return (
    <div className="workspace-root">
      <div className="h-full w-full flex flex-col relative">
        <Header
          voiceState={voiceState}
          onToggleRecording={toggleVoice}
          onNavigateHome={onNavigateHome}
          online={online}
          breadcrumb={{ project: session?.title ?? "local session", file: FILE_NAME }}
        />

        {voiceState !== "idle" && (
          <div
            className={`shrink-0 h-6 border-b flex items-center justify-center gap-2 text-[10.5px] font-medium ${
              voiceState === "recording"
                ? "bg-red-950/30 border-red-900/50 text-red-300"
                : "bg-sky-950/30 border-sky-900/50 text-sky-300"
            }`}
          >
            <span
              className={`w-1.5 h-1.5 rounded-full pulse-dot ${
                voiceState === "recording" ? "bg-red-500" : "bg-sky-500"
              }`}
              aria-hidden
            />
            {voiceState === "recording"
              ? "Recording on-device — click the mic again to stop and transcribe."
              : "Transcribing your dictation on the local engine…"}
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
            cells={cells}
            online={online}
            adding={adding}
            onChange={changeCellContent}
            onRun={runCellNow}
            onCancel={cancelRun}
            onClear={clearCell}
            onFocusCell={focusCell}
            onAddCell={addCell}
          />
          <CoPilotPane
            mode={mode}
            onModeChange={changeMode}
            thread={thread}
            busy={aiBusy}
            onSend={askTutor}
            draft={draft}
            onDraftChange={setDraft}
          />
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
