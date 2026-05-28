import { I } from "./icons";

type Props = {
  cellLabel: string;
  language: string;
  content: string;
  onChange: (content: string) => void;
  running: boolean;
  /** Terminal text from the last run (CellRead.last_output), or null. */
  output: string | null;
  /** Backend cell status: ok | error | terminated | timeout | "" (never run). */
  status: string;
  /** Set when a run request was aborted client-side; the server job continues. */
  note: string | null;
  onRun: () => void;
  onCancel: () => void;
  onClear: () => void;
};

const LINE_HEIGHT = 24; // leading-6

function statusTone(status: string): string {
  if (status === "ok") return "text-emerald-400";
  if (status === "error" || status === "terminated") return "text-red-400";
  if (status === "timeout") return "text-amber-400";
  return "text-zinc-400";
}

export function NotebookPane({
  cellLabel,
  language,
  content,
  onChange,
  running,
  output,
  status,
  note,
  onRun,
  onCancel,
  onClear,
}: Props) {
  const lineCount = Math.max(content.split("\n").length, 1);
  const hasOutput = output != null && output.length > 0;

  return (
    <main className="flex-1 min-w-0 flex flex-col" style={{ background: "var(--bg-canvas)" }} aria-label="Notebook">
      <div className="h-9 shrink-0 flex items-center border-b border-zinc-900 bg-zinc-950 px-3 justify-between">
        <div className="flex items-center gap-1.5 text-[11px] font-medium text-zinc-200">
          <I.File size={12} className="text-zinc-500" />
          <span>scratchpad.{language === "python" ? "py" : language}</span>
        </div>
        <div className="text-[11px] font-mono text-zinc-500">{language} · loopback mode</div>
      </div>

      <div className="flex-1 overflow-y-auto p-4 max-w-4xl w-full mx-auto space-y-4">
        <div className="rounded border border-zinc-900 bg-zinc-950 overflow-hidden">
          <div className="h-8 bg-zinc-900/40 border-b border-zinc-900 px-3 flex items-center justify-between">
            <span className="text-[10px] font-mono tracking-wider font-semibold uppercase text-zinc-400">
              {cellLabel} · {language}
            </span>
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={onRun}
                disabled={running}
                aria-label="Run cell"
                className="h-5 px-2 rounded bg-zinc-900 hover:bg-zinc-800 border border-zinc-800 text-emerald-400 text-[11px] font-medium flex items-center gap-1 disabled:opacity-50 transition-colors duration-150"
              >
                <I.Play size={9} /> Run
              </button>
              <button
                type="button"
                onClick={onCancel}
                disabled={!running}
                aria-label="Cancel run request"
                title="Cancels the client request; the server job continues to completion"
                className="h-5 px-2 rounded bg-zinc-900 hover:bg-zinc-800 border border-zinc-800 text-zinc-300 text-[11px] font-medium flex items-center gap-1 disabled:opacity-40 transition-colors duration-150"
              >
                <I.Stop size={9} /> Cancel
              </button>
              <button
                type="button"
                onClick={onClear}
                className="h-5 px-2 rounded bg-zinc-900 hover:bg-zinc-800 border border-zinc-800 text-zinc-400 text-[11px] font-medium transition-colors duration-150"
              >
                Clear
              </button>
            </div>
          </div>

          <div className="bg-zinc-950 px-1">
            <div className="flex py-3 font-mono text-[13px] leading-6">
              <div aria-hidden className="shrink-0 select-none">
                {Array.from({ length: lineCount }, (_, i) => (
                  <div
                    key={i}
                    className="h-6 w-11 pr-4 text-right text-zinc-700 text-[11px] font-sans font-medium leading-6"
                  >
                    {i + 1}
                  </div>
                ))}
              </div>
              <textarea
                value={content}
                onChange={(e) => onChange(e.target.value)}
                spellCheck={false}
                wrap="off"
                aria-label={`${cellLabel} source`}
                className="flex-1 resize-none bg-transparent text-zinc-300 outline-none border-0 p-0 whitespace-pre overflow-hidden leading-6"
                style={{ height: lineCount * LINE_HEIGHT }}
              />
            </div>
          </div>

          <div
            className="border-t border-zinc-900 p-3 font-mono text-[12px] leading-relaxed min-h-[132px]"
            style={{ background: "var(--bg-inset)" }}
            role="log"
            aria-live="polite"
            aria-label="Cell output"
          >
            {running && (
              <div className="text-zinc-400 flex items-center gap-2">
                <span className="w-1.5 h-1.5 rounded-full bg-amber-500 pulse-dot" aria-hidden />
                <span>Running on the local engine via loopback…</span>
              </div>
            )}

            {!running && !hasOutput && (
              <div className="text-zinc-700 select-none">
                <span>$ ./engine_worker</span>
                <p className="text-[11px] mt-1 text-zinc-700 italic">No output recorded. Press Run.</p>
              </div>
            )}

            {!running && hasOutput && (
              <>
                <div className={`mb-1.5 text-[10px] font-semibold uppercase tracking-wider ${statusTone(status)}`}>
                  Exited · {status || "unknown"}
                </div>
                <pre className="whitespace-pre-wrap text-zinc-200 m-0">{output}</pre>
              </>
            )}

            {note && <p className="mt-2 text-[11px] text-amber-400/90 italic">{note}</p>}
          </div>
        </div>

        <button
          type="button"
          disabled
          title="Multi-cell notebooks are on the roadmap"
          className="w-full h-9 rounded border border-dashed border-zinc-800 text-zinc-600 text-[12px] font-medium flex items-center justify-center gap-1.5 cursor-not-allowed"
        >
          <I.Plus size={13} /> Add cell — coming soon
        </button>
      </div>
    </main>
  );
}
