import { useState } from "react";
import type { AiMode } from "../types";
import { I } from "./icons";

export type ChatMessage = {
  id: string;
  role: "student" | "tutor";
  text: string;
  /** true while a tutor reply is still streaming in. */
  streaming?: boolean;
  /** true when the reply could not be produced (backend down / error). */
  errored?: boolean;
};

// FR-AI-6: the backend prefixes a full copy-pasteable solution with this exact
// marker line. We detect it to raise the integrity banner and hide the raw
// marker from the rendered answer.
const FULL_SOLUTION_PREFIX = "[FULL SOLUTION";

const MODELS = ["Gemma 4 E4B (active)", "Gemma 4 26B A4B (MoE)"];

type Props = {
  mode: AiMode;
  onModeChange: (mode: AiMode) => void;
  thread: ChatMessage[];
  /** true while a Direct-mode answer is streaming. */
  busy: boolean;
  onSend: (question: string) => void;
};

function TutorMessage({ message, socratic }: { message: ChatMessage; socratic: boolean }) {
  const isSolution = message.text.startsWith(FULL_SOLUTION_PREFIX);
  // Drop the marker's own line; show the explanation beneath the banner.
  const body = isSolution ? message.text.slice(message.text.indexOf("\n") + 1).trimStart() : message.text;

  return (
    <div className={`space-y-2 border-l-2 pl-3 ${socratic ? "border-amber-800/60" : "border-sky-800/60"}`}>
      <div className="flex items-center gap-1.5 text-[10px] font-mono font-semibold tracking-wider text-zinc-300 uppercase">
        <I.Bot size={11} className={socratic ? "text-amber-400" : "text-sky-400"} />
        <span>Whetstone Tutor</span>
      </div>

      {isSolution && (
        <div className="flex items-start gap-1.5 text-[10px] text-sky-300/90 font-medium">
          <I.Alert size={11} className="mt-px shrink-0" />
          <span>Integrity note: this is a complete solution, not a hint.</span>
        </div>
      )}

      <div className="text-[12.5px] text-zinc-300 leading-relaxed whitespace-pre-wrap">
        {message.errored ? <span className="text-red-400">{body}</span> : body}
        {message.streaming && <span className="inline-block w-1.5 h-3 ml-0.5 align-middle bg-zinc-500 pulse-dot" />}
      </div>
    </div>
  );
}

export function CoPilotPane({ mode, onModeChange, thread, busy, onSend }: Props) {
  const socratic = mode === "socratic";
  const [thinkingOpen, setThinkingOpen] = useState(false);
  const [model, setModel] = useState(MODELS[0]);
  const [draft, setDraft] = useState("");

  const submit = () => {
    const q = draft.trim();
    if (!q || busy) return;
    onSend(q);
    setDraft("");
  };

  return (
    <aside className="w-[360px] shrink-0 border-l border-zinc-900 bg-zinc-950 flex flex-col" aria-label="AI co-pilot">
      <div className="p-2 border-b border-zinc-900">
        <div role="tablist" aria-label="Tutor mode" className="bg-zinc-900 p-0.5 rounded flex text-center">
          <button
            type="button"
            role="tab"
            aria-selected={!socratic}
            onClick={() => onModeChange("direct")}
            className={`flex-1 py-1.5 text-[11px] font-semibold rounded transition-all duration-200 ${
              !socratic ? "bg-zinc-800 text-sky-300 shadow-sm" : "text-zinc-500 hover:text-zinc-300"
            }`}
          >
            Direct Help
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={socratic}
            onClick={() => onModeChange("socratic")}
            className={`flex-1 py-1.5 text-[11px] font-semibold rounded transition-all duration-200 ${
              socratic ? "bg-zinc-800 text-amber-300 shadow-sm" : "text-zinc-500 hover:text-zinc-300"
            }`}
          >
            Socratic Mode
          </button>
        </div>
      </div>

      <div className="px-3 py-1.5 bg-zinc-900/20 border-b border-zinc-900 flex items-center justify-between text-[10px] font-mono text-zinc-400">
        <label className="flex items-center gap-1.5">
          <span className="sr-only">Active model</span>
          <select
            aria-label="Active local model"
            value={model}
            onChange={(e) => setModel(e.target.value)}
            className="bg-transparent text-zinc-300 border-0 focus:outline-none cursor-pointer"
          >
            {MODELS.map((m) => (
              <option key={m}>{m}</option>
            ))}
          </select>
        </label>
        <span>128K context</span>
      </div>

      <div
        className={`flex-1 overflow-y-auto px-4 py-4 space-y-4 transition-colors duration-300 ${
          socratic ? "bg-amber-950/[0.04]" : "bg-sky-950/[0.04]"
        }`}
      >
        {thread.length === 0 && (
          <p className="text-[12px] text-zinc-500 leading-relaxed">
            {socratic
              ? "Ask the local co-pilot about your code or the tracked requirements. In Socratic mode it replies with guiding questions and graded hints rather than the full answer — on-device and grounded in this session."
              : "Ask the local co-pilot about your code or the tracked requirements. Answers stream from the on-device model and are grounded in this session."}
          </p>
        )}

        {thread.map((m) =>
          m.role === "student" ? (
            <div key={m.id} className="space-y-1">
              <div className="flex items-center gap-1.5 text-[10px] font-mono font-semibold tracking-wider text-zinc-400 uppercase">
                <I.User size={10} /> <span>Student</span>
              </div>
              <p className="text-[12.5px] text-zinc-300 leading-relaxed whitespace-pre-wrap">{m.text}</p>
            </div>
          ) : (
            <TutorMessage key={m.id} message={m} socratic={socratic} />
          ),
        )}

        {thread.length > 0 && (
          <div className="rounded border border-zinc-900 bg-zinc-900/30">
            <button
              type="button"
              onClick={() => setThinkingOpen((o) => !o)}
              aria-expanded={thinkingOpen}
              className="w-full flex items-center justify-between px-2.5 py-1.5 text-[10.5px] font-mono text-zinc-400 hover:text-zinc-200 transition-colors duration-150"
            >
              <span>About the tutor's reasoning…</span>
              <I.Down size={11} className={`transition-transform duration-200 ${thinkingOpen ? "rotate-180" : ""}`} />
            </button>
            {thinkingOpen && (
              <div className="px-2.5 pb-2.5 pt-0.5 text-[10.5px] font-mono text-zinc-500 leading-relaxed border-t border-zinc-900">
                The tutor streams its reply as it is generated. The local model's separate chain-of-thought isn't
                exposed by <span className="font-mono">/ai/ask</span>, so only the final reply is shown here.
              </div>
            )}
          </div>
        )}
      </div>

      <div className="p-3 border-t border-zinc-900 bg-zinc-950">
        <div
          className={`flex items-center border bg-zinc-900/60 rounded transition-colors duration-200 px-2 py-1.5 focus-within:border-zinc-600 ${
            socratic ? "border-amber-900/50" : "border-sky-900/50"
          }`}
        >
          <input
            type="text"
            aria-label="Ask the tutor a question"
            disabled={busy}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") submit();
            }}
            placeholder={busy ? "Waiting for the tutor…" : "Ask the tutor anything…"}
            className="flex-1 bg-transparent border-0 text-[12px] text-zinc-200 placeholder-zinc-600 focus:outline-none disabled:cursor-not-allowed"
          />
          <button
            type="button"
            onClick={submit}
            disabled={busy || !draft.trim()}
            aria-label="Send message"
            className="p-1 text-zinc-500 hover:text-zinc-200 transition-colors duration-150 disabled:opacity-40 disabled:hover:text-zinc-500"
          >
            <I.Send size={12} />
          </button>
        </div>
      </div>
    </aside>
  );
}
